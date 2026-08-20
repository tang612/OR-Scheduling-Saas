"""RQ 任务：异步求解 + 进度推送（Redis pub/sub）+ 取消检查 + 幂等持久化。

进度写入分层（第一性原理审查修订 §6）：
- 实时：progress → Redis PUBLISH（SSE 四段式）
- 持久化：MongoDB tasks.progress 仅阶段切换/完成时落粗粒度快照
- 取消：Redis 标志位 task:{id}:cancel（跨进程可见，threading.Event 跨进程失效已规避）
- 幂等：solutions 以 (task_id, engine) 唯一键，worker 崩溃重试不重复写
"""
import json
from datetime import datetime, timezone

from bson import ObjectId

from scheduler.model import DataError, feasibility_check

from app.core.redis import cancel_key, get_redis, task_channel
from app.db.mongo import collections
from app.services.solver_service import dataset_to_data_model, run_solve_sync


def _publish(task_id: str, event: dict) -> None:
    get_redis().publish(task_channel(task_id), json.dumps(event, ensure_ascii=False))


def run_solve_job(task_id: str, dataset_data: dict, config: dict) -> None:
    """RQ job 入口：构建 → 求解（进度/取消回调）→ 持久化。"""
    cols = collections()
    oid = ObjectId(task_id)

    def progress(percent: float, stage: str) -> None:
        _publish(task_id, {"type": "progress", "percent": round(percent, 3), "stage": stage})
        # 仅阶段切换/完成时落库粗粒度快照（避免高频写 MongoDB）
        if stage != "ALNS迭代" or percent >= 1.0:
            cols["tasks"].update_one({"_id": oid}, {"$set": {
                "progress": round(percent, 3), "stage": stage,
            }})

    def cancel() -> bool:
        return get_redis().get(cancel_key(task_id)) is not None

    cols["tasks"].update_one({"_id": oid}, {"$set": {
        "status": "running", "started_at": datetime.now(timezone.utc),
    }})

    # 数据体检
    try:
        dm = dataset_to_data_model(dataset_data)
        feasibility_check(dm)
    except DataError as e:
        cols["tasks"].update_one({"_id": oid}, {"$set": {
            "status": "failed", "error": {"code": e.code, "msg": e.msg},
            "finished_at": datetime.now(timezone.utc),
        }})
        _publish(task_id, {"type": "failed", "error": {"code": e.code, "msg": e.msg}})
        return

    # 求解
    try:
        result = run_solve_sync(
            dm, weights=tuple(config.get("weights", (0.0, 1.0, 0.0))),
            time_budget=config.get("time_budget"), seed=config.get("seed", 42),
            solver=config.get("solver", "auto"),
            progress_cb=progress, cancel=cancel,
        )
    except Exception as e:  # noqa: BLE001 —— 求解器异常持久化后返回
        cols["tasks"].update_one({"_id": oid}, {"$set": {
            "status": "failed", "error": {"code": "ERR_SOLVER", "msg": str(e)},
            "finished_at": datetime.now(timezone.utc),
        }})
        _publish(task_id, {"type": "failed", "error": {"code": "ERR_SOLVER", "msg": str(e)}})
        return

    # 取消检查：求解被 cancel 中断时，标记 cancelled（不覆盖为 succeeded）
    if cancel():
        cols["tasks"].update_one({"_id": oid}, {"$set": {
            "status": "cancelled", "stage": "已取消",
            "finished_at": datetime.now(timezone.utc),
        }})
        _publish(task_id, {"type": "cancelled"})
        return

    # 幂等持久化 solution（task_id+engine 唯一；all 模式写多方案）
    task = cols["tasks"].find_one({"_id": oid})
    now = datetime.now(timezone.utc)
    results = result if isinstance(result, list) else [result]
    solution_ids = []
    for r in results:
        solution_doc = {
            "task_id": oid,
            "tenant_id": task["tenant_id"],
            "engine": r["solver"],
            "status": r["status"],
            "objective": r["objective"],
            "gap": r["gap"],
            "solve_time_s": r["solve_time_s"],
            "schedule": r["schedule"],
            "created_at": now,
        }
        existing = cols["solutions"].find_one(
            {"task_id": oid, "engine": r["solver"]}
        )
        if existing is None:
            solution_ids.append(cols["solutions"].insert_one(solution_doc).inserted_id)
        else:
            solution_ids.append(existing["_id"])

    # 摘要：多方案取目标最优者作为 task 目标
    best = min(results, key=lambda r: (r["objective"]["total"] if r["objective"]["total"] is not None else float("inf")))
    cols["tasks"].update_one({"_id": oid}, {"$set": {
        "status": "succeeded", "progress": 1.0, "stage": "完成",
        "solver": "multi" if len(results) > 1 else results[0]["solver"],
        "objective": best["objective"],
        "solution_id": solution_ids[0] if len(solution_ids) == 1 else None,
        "finished_at": now,
    }})
    _publish(task_id, {"type": "done", "solution_ids": [str(s) for s in solution_ids]})
