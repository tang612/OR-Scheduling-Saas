"""任务路由：异步提交（RQ 入队）+ 详情 + 列表 + SSE 实时进度 + 取消。

M2：POST 改为入队（202 + pending），worker 异步求解；
SSE 四段式（Worker→Redis pub/sub→API→浏览器）；DELETE 设置取消标志。
"""
import json
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response, StreamingResponse
from rq import Queue

from scheduler.model import DataError, feasibility_check

from ...core.deps import get_collections, get_current_user
from ...core.redis import cancel_key, get_redis, task_channel
from ...models.schemas import TaskCreate, TaskOut
from ...services.solver_service import dataset_to_data_model

router = APIRouter(prefix="/tasks", tags=["tasks"])

# 队列分级：数据规模决定求解器，也决定队列（CPU 资源隔离）
_QUEUES = {20: "quick", 80: "alns300", float("inf"): "alns900"}

# 排队超时阈值（pending 超过该秒数未拾取 → 前端高亮警告）
QUEUE_TIMEOUT_S = 300


def _queue_name(n: int) -> str:
    for limit in sorted(_QUEUES):
        if n <= limit:
            return _QUEUES[limit]
    return "alns900"


def _is_queue_timeout(t: dict) -> bool:
    """惰性检测：pending 且超阈值 → 排队超时（不改 status，仅提示标记）。"""
    if t.get("status") != "pending" or t.get("created_at") is None:
        return False
    elapsed = (datetime.now(timezone.utc) - t["created_at"]).total_seconds()
    return elapsed > QUEUE_TIMEOUT_S


def _queue_position(cols: dict, t: dict) -> int | None:
    """任务在队列中的位置（前面还有几个任务）；非 pending 或无队列返回 None。"""
    if t.get("status") != "pending":
        return None
    ds = cols["datasets"].find_one({"_id": t["dataset_id"]})
    if ds is None:
        return None
    n = len(ds["data"]["orders"])
    try:
        ids = Queue(_queue_name(n), connection=get_redis()).get_job_ids()
    except Exception:  # noqa: BLE001 —— 队列查询失败不阻塞详情返回
        return None
    task_id = str(t["_id"])
    if task_id in ids:
        return ids.index(task_id)
    return None


def _to_out(t: dict) -> TaskOut:
    return TaskOut(
        id=str(t["_id"]), tenant_id=str(t["tenant_id"]), name=t["name"],
        dataset_id=str(t["dataset_id"]), status=t["status"],
        progress=t.get("progress", 0.0), stage=t.get("stage", ""),
        solver=t.get("solver"), objective=t.get("objective"),
        error=t.get("error"), created_at=t["created_at"],
        dispatched_at=t.get("dispatched_at"),
        finished_at=t.get("finished_at"),
        queue_position=None,   # get_task 惰性计算后覆盖
        queue_timeout=_is_queue_timeout(t),
        timeline=t.get("timeline") or [],
    )


@router.post("", status_code=202, response_model=TaskOut)
def create_task(
    body: TaskCreate,
    user=Depends(get_current_user),
    cols=Depends(get_collections),
) -> TaskOut:
    ds = cols["datasets"].find_one(
        {"_id": ObjectId(body.dataset_id), "tenant_id": user["tenant_id"]}
    )
    if ds is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "数据集不存在")

    # 预检（数据体检 + 可行性），422 提前返回
    try:
        dm = dataset_to_data_model(ds["data"])
        feasibility_check(dm)
    except DataError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"[{e.code}] {e.msg}")

    now = datetime.now(timezone.utc)
    task_doc = {
        "tenant_id": user["tenant_id"],
        "user_id": user["_id"],
        "name": body.name,
        "dataset_id": ObjectId(body.dataset_id),
        "config": body.config.model_dump(by_alias=True),
        "status": "pending",
        "progress": 0.0,
        "stage": "排队中",
        "solver": None,
        "objective": None,
        "error": None,
        "solution_id": None,
        "created_at": now,
        "started_at": None,
        "finished_at": None,
    }
    task_id = cols["tasks"].insert_one(task_doc).inserted_id

    # 入队（job_id=task_id 幂等；job_timeout 覆盖 ALNS 900s + 余量）
    job_config = {
        "weights": tuple(body.config.weights),
        "time_budget": body.config.time_budget,
        "seed": body.config.seed,
        "solver": body.config.solver,
    }
    q = Queue(_queue_name(dm.n), connection=get_redis())
    q.enqueue(
        "worker.tasks.run_solve_job",
        str(task_id), ds["data"], job_config,
        job_id=str(task_id), job_timeout=1200, result_ttl=60,
    )

    return _to_out(cols["tasks"].find_one({"_id": task_id}))


@router.get("", response_model=list[TaskOut])
def list_tasks(
    user=Depends(get_current_user),
    cols=Depends(get_collections),
) -> list[TaskOut]:
    docs = cols["tasks"].find({"tenant_id": user["tenant_id"]}).sort("created_at", -1).limit(100)
    return [_to_out(t) for t in docs]


@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: str,
    user=Depends(get_current_user),
    cols=Depends(get_collections),
) -> TaskOut:
    t = cols["tasks"].find_one(
        {"_id": ObjectId(task_id), "tenant_id": user["tenant_id"]}
    )
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    out = _to_out(t)
    out.queue_position = _queue_position(cols, t)
    return out


@router.get("/{task_id}/logs.txt")
def task_logs_txt(
    task_id: str,
    user=Depends(get_current_user),
    cols=Depends(get_collections),
) -> Response:
    """导出任务全量求解日志（TXT）。成功：solution.logs；失败/取消：tasks.logs。"""
    t = cols["tasks"].find_one(
        {"_id": ObjectId(task_id), "tenant_id": user["tenant_id"]}
    )
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")

    lines: list[str] = []
    for s in cols["solutions"].find({"task_id": ObjectId(task_id)}):
        lines.extend(s.get("logs") or [])
    if not lines:
        lines = t.get("logs") or []
    if not lines:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "该任务无日志记录")

    content = "\n".join(lines) + "\n"
    return Response(
        content=content, media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="task-{task_id}-logs.txt"'},
    )


@router.get("/{task_id}/events")
def task_events(
    task_id: str,
    user=Depends(get_current_user),
    cols=Depends(get_collections),
) -> StreamingResponse:
    """SSE 实时进度：先发快照，再订阅 Redis pub/sub 增量。"""
    task = cols["tasks"].find_one(
        {"_id": ObjectId(task_id), "tenant_id": user["tenant_id"]}
    )
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")

    r = get_redis()
    channel = task_channel(task_id)

    def gen():
        # 快照（断线重连/首次连接：先给当前状态 + 时间线 + 排队信息）
        yield "data: " + json.dumps({
            "type": "snapshot",
            "status": task.get("status"),
            "progress": task.get("progress", 0.0),
            "stage": task.get("stage", ""),
            "timeline": task.get("timeline") or [],
            "dispatched_at": task.get("dispatched_at"),
            "queue_timeout": _is_queue_timeout(task),
        }, ensure_ascii=False, default=str) + "\n\n"

        # 已终态：直接结束（不订阅，避免错过 done 事件后阻塞）
        if task.get("status") in ("succeeded", "failed", "cancelled"):
            return

        pubsub = r.pubsub()
        pubsub.subscribe(channel)
        try:
            for msg in pubsub.listen():
                if msg["type"] != "message":
                    continue
                yield "data: " + msg["data"] + "\n\n"
                # 终态事件后结束流
                if '"type": "done"' in msg["data"] or '"type": "failed"' in msg["data"]:
                    break
        finally:
            pubsub.unsubscribe(channel)
            pubsub.close()

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.delete("/{task_id}", status_code=204)
def cancel_task(
    task_id: str,
    user=Depends(get_current_user),
    cols=Depends(get_collections),
) -> None:
    task = cols["tasks"].find_one(
        {"_id": ObjectId(task_id), "tenant_id": user["tenant_id"]}
    )
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")

    # 设置取消标志（worker 求解循环内检查）；终态任务直接返回
    if task["status"] in ("pending", "running"):
        get_redis().set(cancel_key(task_id), "1", ex=3600)
        cols["tasks"].update_one({"_id": ObjectId(task_id)}, {"$set": {
            "status": "cancelled",
            "stage": "已取消",
            "finished_at": datetime.now(timezone.utc),
        }})
