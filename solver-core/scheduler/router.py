"""求解器路由（数据决定模型）与统一 solve 接口。

实测结论（反幻觉：以数据为准）：
- n ≤ 20   → CP-SAT 精确（L1/L2 秒级最优，手工验证锚点）
- n ≤ 80   → 构造 + ALNS 300s（L3：实测 ALNS 60s ΣT=7280 优于 CP-SAT 300s ΣT=7828）
- n ≤ 300  → 构造 + ALNS 900s（L4）
- else     → 构造 + ALNS 900s（L5）
"""
from __future__ import annotations

import time

from .model import DataModel, Schedule
from . import cp_sat
from . import heuristics


def solve(data: DataModel, lambda_: tuple = (0.0, 1.0, 0.0),
          time_budget: float | None = None, seed: int = 42,
          verbose: bool = True, progress_cb=None, cancel=None,
          log_cb=None) -> dict:
    """统一求解入口，按规模自动路由。

    progress_cb(percent, stage)：进度回调（可选，透传子求解器）。
    cancel() -> bool：取消检查（可选，透传子求解器）。
    log_cb(line: str)：求解日志行回调（可选，CP-SAT 实时日志流）。
    """
    n = data.n
    t0 = time.time()

    if n <= 20:
        if verbose:
            print(f"[路由] n={n} → CP-SAT 精确求解")
        result = cp_sat.solve(data, lambda_, time_limit=None, verbose=verbose,
                              progress_cb=progress_cb, cancel=cancel, log_cb=log_cb)
        result["solver"] = "CP-SAT"
        result["total_time_s"] = time.time() - t0
        return result

    budget = time_budget if time_budget else (300.0 if n <= 80 else 900.0)
    if verbose:
        print(f"[路由] n={n} → 构造启发式 + ALNS ({budget:.0f}s)")
    result = _metaheuristic(data, lambda_, budget, seed, verbose, progress_cb, cancel)
    result["total_time_s"] = time.time() - t0
    return result


def _metaheuristic(data: DataModel, lambda_: tuple, budget: float,
                   seed: int, verbose: bool, progress_cb=None, cancel=None) -> dict:
    s0_best = None
    for s_seed in range(3):
        s0 = heuristics.constructive(data, lambda_, seed=seed + s_seed)
        if s0 is None or not s0.feasible:
            continue
        if s0_best is None or _obj(s0, lambda_) < _obj(s0_best, lambda_):
            s0_best = s0

    if s0_best is None or not s0_best.feasible:
        return {
            "status": "INFEASIBLE", "schedule": None,
            "makespan": None, "tardiness": None, "completion": None,
            "objective": None, "gap": None, "solver": "构造启发式",
            "solve_time_s": 0.0,
            "initial_objective": None, "convergence": [], "iteration_log": [],
            "operator_stats": [], "iterations": 0, "termination": "infeasible",
            "note": "构造启发式未找到可行解（null 切换约束过紧）",
        }

    # 追踪模式：收敛曲线 + 迭代日志 + 算子贡献度（Dashboard 优化分析数据源）
    trace = heuristics.alns(data, s0_best, lambda_, time_limit=budget,
                            seed=seed, verbose=verbose,
                            progress_cb=progress_cb, cancel=cancel,
                            return_trace=True)
    s_best = trace["schedule"]
    # Dashboard 优化分析（启发式专属）：初始解 / 收敛曲线 / 迭代日志 / 算子贡献。
    # 收敛曲线与迭代日志在落库前抽稀（超大数据集可达数万点，前端渲染与存储受限）
    conv_raw = [{"iter": it, "objective": obj} for it, obj, _ in trace["history"]]
    convergence = [{"iter": c["iter"], "objective": c["objective"]}
                   for c in cp_sat._thin(conv_raw, 500)]
    return {
        "status": "FEASIBLE",
        "schedule": s_best,
        "makespan": s_best.makespan,
        "tardiness": s_best.tardiness,
        "completion": s_best.completion,
        "objective": _obj(s_best, lambda_),
        "gap": None,  # 元启发无下界（反幻觉：不伪造 gap）
        "solver": f"构造+ALNS({budget:.0f}s)",
        "solve_time_s": budget,
        "initial_objective": {
            "makespan": s0_best.makespan, "tardiness": s0_best.tardiness,
            "completion": s0_best.completion, "total": _obj(s0_best, lambda_),
        },
        "convergence": convergence,
        "iteration_log": _cap_iteration_log(trace["iteration_log"], 2000),
        "operator_stats": trace["operator_stats"],
        "iterations": trace["iterations"],
        "termination": trace["termination"],
    }


def _obj(s: Schedule, lambda_: tuple) -> float:
    return lambda_[0] * s.makespan + lambda_[1] * s.tardiness + lambda_[2] * s.completion


def _cap_iteration_log(log: list, cap: int = 2000):
    """迭代日志截断：改进事件全保留，非改进事件等间隔抽稀（保首尾）。"""
    if len(log) <= cap:
        return log
    improved = [e for e in log if e["improved"]]
    if len(improved) >= cap:
        return improved[:cap]
    rest = [e for e in log if not e["improved"]]
    keep = cap - len(improved)
    step = len(rest) / keep if rest else 1.0
    sampled = [rest[int(i * step)] for i in range(keep - 1)] + ([rest[-1]] if rest else [])
    merged = improved + sampled
    merged.sort(key=lambda e: e["iter"])
    return merged
