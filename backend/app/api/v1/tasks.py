"""任务路由：异步提交（RQ 入队）+ 详情 + 列表 + SSE 实时进度 + 取消。

M2：POST 改为入队（202 + pending），worker 异步求解；
SSE 四段式（Worker→Redis pub/sub→API→浏览器）；DELETE 设置取消标志。
"""
import json
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from rq import Queue

from scheduler.model import DataError, feasibility_check

from ...core.deps import get_collections, get_current_user
from ...core.redis import cancel_key, get_redis, task_channel
from ...models.schemas import TaskCreate, TaskOut
from ...services.solver_service import dataset_to_data_model

router = APIRouter(prefix="/tasks", tags=["tasks"])

# 队列分级：数据规模决定求解器，也决定队列（CPU 资源隔离）
_QUEUES = {20: "quick", 80: "alns300", float("inf"): "alns900"}


def _queue_name(n: int) -> str:
    for limit in sorted(_QUEUES):
        if n <= limit:
            return _QUEUES[limit]
    return "alns900"


def _to_out(t: dict) -> TaskOut:
    return TaskOut(
        id=str(t["_id"]), tenant_id=str(t["tenant_id"]), name=t["name"],
        dataset_id=str(t["dataset_id"]), status=t["status"],
        progress=t.get("progress", 0.0), stage=t.get("stage", ""),
        solver=t.get("solver"), objective=t.get("objective"),
        error=t.get("error"), created_at=t["created_at"],
        finished_at=t.get("finished_at"),
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
    return _to_out(t)


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
        # 快照（断线重连/首次连接：先给当前状态）
        yield "data: " + json.dumps({
            "type": "snapshot",
            "status": task.get("status"),
            "progress": task.get("progress", 0.0),
            "stage": task.get("stage", ""),
        }, ensure_ascii=False) + "\n\n"

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
