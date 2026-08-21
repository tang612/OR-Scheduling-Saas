"""RQ 任务：异步求解 + 进度/日志推送（Redis pub/sub）+ 取消检查 + 幂等持久化。

Dashboard v2 改造（2026-08）：
- 状态机细化：pending → dispatched（调度中）→ running（求解中）→ 结果处理中 → 终态
- 状态时间线：tasks.timeline 追加每次状态切换（status/stage/at）
- 实时日志：log_cb 批量 PUBLISH {type:"log"}（每 _LOG_BATCH 行，防 pub/sub 风暴）
- 失败/取消日志落库：tasks.logs（成功日志由 solution.logs 承载，环形上限 10000 行）

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

_LOG_BATCH = 20          # 日志批量推送行数（防 pub/sub 风暴）
MAX_LOG_LINES = 10000    # 落库日志环形上限（与 solver-core 采集上限一致）


def _publish(task_id: str, event: dict) -> None:
    get_redis().publish(task_channel(task_id), json.dumps(event, ensure_ascii=False))


def _set_status(cols, oid, task_id, *, status: str, stage: str,
                progress: float | None = None, extra: dict | None = None) -> None:
    """状态切换统一入口：落库（含 timeline 追加）+ SSE 推送 status 事件。"""
    now = datetime.now(timezone.utc)
    set_fields: dict = {"status": status, "stage": stage, "progress": progress}
    if extra:
        set_fields.update(extra)
    cols["tasks"].update_one({"_id": oid}, {
        "$set": set_fields,
        "$push": {"timeline": {"status": status, "stage": stage,
                               "at": now.isoformat()}},
    })
    _publish(task_id, {"type": "status", "status": status, "stage": stage,
                       "at": now.isoformat(), "progress": progress})


def run_solve_job(task_id: str, dataset_data: dict, config: dict) -> None:
    """RQ job 入口：调度中 → 求解（进度/日志/取消回调）→ 结果处理中 → 终态。"""
    cols = collections()
    oid = ObjectId(task_id)

    # 日志实时推送缓冲：批量 PUBLISH（每 _LOG_BATCH 行），结束 flush
    log_buf: list[str] = []

    def _flush_logs() -> None:
        if log_buf:
            _publish(task_id, {"type": "log", "lines": list(log_buf)})
            log_buf.clear()

    def log_line(line: str) -> None:
        line = line.rstrip()
        if not line:
            return
        log_buf.append(line)
        if len(log_buf) >= _LOG_BATCH:
            _flush_logs()

    def progress(percent: float, stage: str) -> None:
        _publish(task_id, {"type": "progress", "percent": round(percent, 3), "stage": stage})
        # 仅阶段切换/完成时落库粗粒度快照（避免高频写 MongoDB）
        if stage != "ALNS迭代" or percent >= 1.0:
            cols["tasks"].update_one({"_id": oid}, {"$set": {
                "progress": round(percent, 3), "stage": stage,
            }})

    def cancel() -> bool:
        return get_redis().get(cancel_key(task_id)) is not None

    # ---- 调度中：已被 worker 拾取，初始化求解上下文 ----
    _set_status(cols, oid, task_id, status="dispatched", stage="调度中",
                progress=0.05, extra={"dispatched_at": datetime.now(timezone.utc)})

    # ---- 求解中 ----
    _set_status(cols, oid, task_id, status="running", stage="求解中", progress=0.1)

    # 数据体检
    try:
        dm = dataset_to_data_model(dataset_data)
        feasibility_check(dm)
    except DataError as e:
        _flush_logs()
        _set_status(cols, oid, task_id, status="failed", stage="求解失败",
                    extra={"error": {"code": e.code, "msg": e.msg},
                           "finished_at": datetime.now(timezone.utc),
                           "logs": list(log_buf)})
        _publish(task_id, {"type": "failed", "error": {"code": e.code, "msg": e.msg}})
        return

    # 求解
    try:
        result = run_solve_sync(
            dm, weights=tuple(config.get("weights", (0.0, 1.0, 0.0))),
            time_budget=config.get("time_budget"), seed=config.get("seed", 42),
            solver=config.get("solver", "auto"),
            progress_cb=progress, cancel=cancel, log_cb=log_line,
        )
    except Exception as e:  # noqa: BLE001 —— 求解器异常持久化后返回
        _flush_logs()
        _set_status(cols, oid, task_id, status="failed", stage="求解失败",
                    extra={"error": {"code": "ERR_SOLVER", "msg": str(e)},
                           "finished_at": datetime.now(timezone.utc),
                           "logs": list(log_buf)})
        _publish(task_id, {"type": "failed", "error": {"code": "ERR_SOLVER", "msg": str(e)}})
        return

    # 取消检查：求解被 cancel 中断时，标记 cancelled（不覆盖为 succeeded）
    if cancel():
        _flush_logs()
        _set_status(cols, oid, task_id, status="cancelled", stage="已取消",
                    extra={"finished_at": datetime.now(timezone.utc),
                           "logs": list(log_buf)})
        _publish(task_id, {"type": "cancelled"})
        return

    # ---- 结果处理中：求解完成，持久化结果 + 生成可视化数据 ----
    _flush_logs()
    progress(0.95, "结果处理中")

    # 幂等持久化 solution（task_id+engine 唯一；all 模式写多方案）
    task = cols["tasks"].find_one({"_id": oid})
    now = datetime.now(timezone.utc)
    results = result if isinstance(result, list) else [result]
    solution_ids = []
    for r in results:
        logs = (r.get("logs") or [])[-MAX_LOG_LINES:]
        # 参数回显：求解器参数 + 提交配置（weights/seed/solver 请求）
        params = dict(r.get("params") or {})
        params.setdefault("engine", r["solver"])
        params["weights"] = list(config.get("weights", (0.0, 1.0, 0.0)))
        params["seed"] = config.get("seed")
        params["solver_request"] = config.get("solver")
        solution_doc = {
            "task_id": oid,
            "tenant_id": task["tenant_id"],
            "engine": r["solver"],
            "status": r["status"],
            "objective": r["objective"],
            "gap": r["gap"],
            "solve_time_s": r["solve_time_s"],
            "schedule": r["schedule"],
            # Dashboard v2 过程数据（启发式：初始解/收敛曲线/迭代日志/算子贡献；
            # 精确：收敛轨迹/终止原因/参数回显/求解日志）
            "initial_objective": r.get("initial_objective"),
            "convergence": r.get("convergence") or [],
            "iteration_log": r.get("iteration_log") or [],
            "operator_stats": r.get("operator_stats") or [],
            "iterations": r.get("iterations"),
            "termination": r.get("termination"),
            "params": params,
            "logs": logs,
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
    _set_status(cols, oid, task_id, status="succeeded", stage="完成",
                progress=1.0, extra={
                    "solver": "multi" if len(results) > 1 else results[0]["solver"],
                    "objective": best["objective"],
                    "solution_id": solution_ids[0] if len(solution_ids) == 1 else None,
                    "finished_at": now,
                })
    _publish(task_id, {"type": "done", "solution_ids": [str(s) for s in solution_ids]})
