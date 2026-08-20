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
          verbose: bool = True) -> dict:
    """统一求解入口，按规模自动路由。"""
    n = data.n
    t0 = time.time()

    if n <= 20:
        if verbose:
            print(f"[路由] n={n} → CP-SAT 精确求解")
        result = cp_sat.solve(data, lambda_, time_limit=None, verbose=verbose)
        result["solver"] = "CP-SAT"
        result["total_time_s"] = time.time() - t0
        return result

    budget = time_budget if time_budget else (300.0 if n <= 80 else 900.0)
    if verbose:
        print(f"[路由] n={n} → 构造启发式 + ALNS ({budget:.0f}s)")
    result = _metaheuristic(data, lambda_, budget, seed, verbose)
    result["total_time_s"] = time.time() - t0
    return result


def _metaheuristic(data: DataModel, lambda_: tuple, budget: float,
                   seed: int, verbose: bool) -> dict:
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
            "note": "构造启发式未找到可行解（null 切换约束过紧）",
        }

    s_best = heuristics.alns(data, s0_best, lambda_, time_limit=budget,
                             seed=seed, verbose=verbose)
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
    }


def _obj(s: Schedule, lambda_: tuple) -> float:
    return lambda_[0] * s.makespan + lambda_[1] * s.tardiness + lambda_[2] * s.completion
