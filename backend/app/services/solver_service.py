"""数据集转换 + 多引擎求解编排。

solver ∈ {auto, cpsat, alns, all}：
- auto：规模路由（n≤20 CP-SAT 精确，否则 构造+ALNS）
- cpsat：强制 CP-SAT 精确（大 n 可能超时）
- alns：强制 构造+ALNS 元启发
- all：跑 cpsat + alns 两引擎，返回结果列表（多方案对比）
"""
from scheduler import cp_sat, router
from scheduler.model import build_data_model


def dataset_to_data_model(dataset_data: dict):
    """把 dataset 的 data dict（machines/orders/recipes/switch_matrix）转成 DataModel。"""
    return build_data_model(
        dataset_data["machines"],
        dataset_data["orders"],
        dataset_data["recipes"],
        dataset_data["switch_matrix"],
    )


def _schedule_to_dict(schedule) -> dict | None:
    """Schedule dataclass → 可存储 dict（甘特图端点据此还原块数据）。"""
    if schedule is None:
        return None
    return {
        "assignment": schedule.assignment,
        "sequences": schedule.sequences,
        "start": schedule.start,
        "end": schedule.end,
    }


def _format(result: dict, solver_name: str) -> dict:
    schedule = result.get("schedule")
    out = {
        "status": result["status"],
        "solver": solver_name,
        "objective": {
            "makespan": result.get("makespan"),
            "tardiness": result.get("tardiness"),
            "completion": result.get("completion"),
            "total": result.get("objective"),
        },
        "gap": result.get("gap"),
        "solve_time_s": result.get("solve_time_s"),
        "schedule": _schedule_to_dict(schedule),
    }
    # Dashboard v2 过程数据透传（白名单：求解器层有则带，无则不出现）
    for k in ("initial_objective", "convergence", "iteration_log", "operator_stats",
              "iterations", "termination", "params", "logs"):
        if result.get(k) is not None:
            out[k] = result[k]
    return out


def _solve_engine(data_model, weights: tuple, time_budget: float | None, seed: int,
                  name: str, progress_cb, cancel, log_cb=None) -> tuple[dict, str]:
    """按引擎名求解，返回 (raw_result, 稳定引擎名)。"""
    if name == "cpsat":
        r = cp_sat.solve(data_model, weights, time_limit=time_budget,
                         progress_cb=progress_cb, cancel=cancel, log_cb=log_cb)
        return r, "CP-SAT"
    if name == "alns":
        budget = time_budget if time_budget else 300.0
        r = router._metaheuristic(data_model, weights, budget, seed, False,
                                  progress_cb, cancel)
        return r, "ALNS"
    # auto：规模路由
    r = router.solve(data_model, lambda_=weights, time_budget=time_budget, seed=seed,
                     progress_cb=progress_cb, cancel=cancel, log_cb=log_cb)
    return r, r.get("solver", "auto")


def run_solve_sync(data_model, weights: tuple, time_budget: float | None, seed: int,
                   solver: str = "auto", progress_cb=None, cancel=None,
                   log_cb=None):
    """同步求解，返回单个 result dict；solver="all" 时返回结果列表。

    progress_cb(percent, stage) / cancel()->bool / log_cb(line) 透传给 solver-core。
    """
    if solver == "all":
        results = []
        for name in ("cpsat", "alns"):
            raw, display = _solve_engine(data_model, weights, time_budget, seed,
                                         name, progress_cb, cancel, log_cb)
            results.append(_format(raw, display))
        return results
    name = solver if solver in ("cpsat", "alns") else "auto"
    raw, display = _solve_engine(data_model, weights, time_budget, seed, name,
                                 progress_cb, cancel, log_cb)
    return _format(raw, display)
