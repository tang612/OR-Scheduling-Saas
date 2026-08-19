"""解质量评价体系：7 项指标计算 + 综合评分 + 迭代追溯快照。

对应方案 V3：
- 指标：GAP、目标函数值、可行性违反、计算耗时、稳定性、负载均衡、可调整弹性
- 综合评分：加权和（权重可配置）
- 迭代追溯：version → change → commit → metrics → delta
"""
from __future__ import annotations

import json
from .model import DataModel, Schedule


# ---------------------------------------------------------------------------
# 问题特定下界（第一性原理：makespan LB + tardiness 单订单 LB + completion LB）
# ---------------------------------------------------------------------------

def lower_bound(data: DataModel, lambda_: tuple) -> float:
    """问题特定下界：LB = λ1·LB_mk + λ2·LB_tard + λ3·LB_comp。"""
    n, m = data.n, data.m
    total_p = sum(data.p)
    # makespan 下界：总负载均分 + 最长单订单
    lb_mk = max(total_p / m, max(data.p) if n > 0 else 0.0)
    # tardiness 下界：单订单延误下界（p_j > d_j 必延误，忽略排队延误）
    lb_tard = sum(max(0.0, data.p[j] - data.d[j]) for j in range(n))
    # completion 下界：ΣC ≥ Σp（每订单完工 ≥ 加工时间）
    lb_comp = float(total_p)
    return lambda_[0] * lb_mk + lambda_[1] * lb_tard + lambda_[2] * lb_comp


# ---------------------------------------------------------------------------
# 扩展指标：负载均衡 + 可调整弹性
# ---------------------------------------------------------------------------

def compute_loads(data: DataModel, sched: Schedule):
    """每机台负载（加工 + 切换 + 清理）。"""
    loads = []
    for mm in range(data.m):
        seq = sched.sequences[mm]
        load = 0.0
        last = None
        for j in seq:
            if last is not None:
                s = data.switch.get((last, data.rho[j]))
                load += (s if s is not None else 0.0) + data.machines[mm].cleanup_time
            load += data.p[j]
            last = data.rho[j]
        loads.append(load)
    return loads


def balance_index(data: DataModel, sched: Schedule) -> float:
    """负载均衡指数：balance = 1 − σ_L/μ_L ∈ [0,1]。"""
    loads = compute_loads(data, sched)
    if not loads:
        return 1.0
    mu = sum(loads) / len(loads)
    if mu <= 0:
        return 1.0
    sigma = (sum((l - mu) ** 2 for l in loads) / len(loads)) ** 0.5
    return max(0.0, 1.0 - sigma / mu)


def flexibility_index(data: DataModel, sched: Schedule) -> float:
    """可调整弹性 = 空闲率 = 1 − 平均负载/makespan ∈ [0,1]。"""
    if sched.makespan <= 0:
        return 0.0
    loads = compute_loads(data, sched)
    mean_load = sum(loads) / len(loads) if loads else 0.0
    return max(0.0, 1.0 - mean_load / sched.makespan)


# ---------------------------------------------------------------------------
# 7 项指标计算
# ---------------------------------------------------------------------------

def compute_metrics(data: DataModel, sched: Schedule, lambda_: tuple,
                    reference: float | None = None,
                    solve_time: float | None = None,
                    all_objectives: list | None = None,
                    time_budget: float = 300.0) -> dict:
    """计算 7 项指标，返回 dict。reference 为参考解目标值（用于相对 GAP）。"""
    obj = (lambda_[0] * sched.makespan + lambda_[1] * sched.tardiness
           + lambda_[2] * sched.completion)
    lb = lower_bound(data, lambda_)

    # 目标函数值归一化（相对下界）
    obj_norm = (obj - lb) / max(abs(lb), 1.0)

    # GAP：优先参考解，其次下界
    gap = None
    gap_type = None
    if reference is not None:
        gap = (obj - reference) / max(abs(reference), 1e-9)
        gap_type = "reference"
    elif lb > 0:
        gap = (obj - lb) / max(abs(lb), 1e-9)
        gap_type = "lower_bound"

    # 可行性违反：硬违反=0（算法保证可行）；软违反=ΣT（交期延误）
    hard_violation = 0.0 if sched.feasible else 1.0
    soft_violation = float(sched.tardiness)

    # 稳定性：多次运行 CV
    cv = 0.0
    if all_objectives and len(all_objectives) >= 3:
        mu = sum(all_objectives) / len(all_objectives)
        sigma = (sum((f - mu) ** 2 for f in all_objectives)
                 / len(all_objectives)) ** 0.5
        cv = sigma / (abs(mu) + 1e-9)

    balance = balance_index(data, sched)
    flex = flexibility_index(data, sched)

    return {
        "objective": obj,
        "obj_norm": obj_norm,
        "makespan": sched.makespan,
        "tardiness": sched.tardiness,
        "completion": sched.completion,
        "gap": gap,
        "gap_type": gap_type,
        "hard_violation": hard_violation,
        "soft_violation": soft_violation,
        "solve_time": solve_time,
        "cv": cv,
        "balance": balance,
        "flex": flex,
        "lower_bound": lb,
    }


# ---------------------------------------------------------------------------
# 综合评分
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS = {
    "obj": 0.30, "gap": 0.15, "feas": 0.10, "time": 0.05,
    "stab": 0.10, "balance": 0.15, "flex": 0.15,
}


def compute_score(metrics: dict, weights: dict | None = None,
                  time_budget: float = 300.0) -> float:
    """综合评分 = Σ w_i·score_i，全部映射到 [0,1]。"""
    w = weights or DEFAULT_WEIGHTS
    score = 0.0
    # 目标函数值：归一化越小越好
    score += w.get("obj", 0) * (1.0 / (1.0 + metrics["obj_norm"]))
    # GAP：越小越好（可能为负 = 优于参考解）
    if metrics["gap"] is not None:
        score += w.get("gap", 0) * (1.0 / (1.0 + max(0.0, metrics["gap"])))
    # 可行性：硬违反=0，软违反归一化
    if metrics["hard_violation"] > 0:
        feas = 0.0
    else:
        feas = 1.0 / (1.0 + metrics["soft_violation"]
                      / max(1.0, metrics["lower_bound"] + 1.0))
    score += w.get("feas", 0) * feas
    # 耗时
    t = metrics["solve_time"] or 0.0
    score += w.get("time", 0) * (1.0 / (1.0 + t / time_budget))
    # 稳定性
    score += w.get("stab", 0) * (1.0 / (1.0 + metrics["cv"]))
    # 负载均衡 + 弹性
    score += w.get("balance", 0) * metrics["balance"]
    score += w.get("flex", 0) * metrics["flex"]
    return score


# ---------------------------------------------------------------------------
# 迭代追溯快照
# ---------------------------------------------------------------------------

def snapshot(version: str, change: str, commit: str, instance: str,
             reference: dict, config: dict, metrics: dict,
             prev_metrics: dict | None = None) -> dict:
    """版本化评测快照 + 与上一版增量。"""
    delta = None
    if prev_metrics is not None:
        delta = {}
        for k in ("objective", "makespan", "tardiness", "completion",
                  "balance", "flex", "cv"):
            if k in metrics and k in prev_metrics:
                delta[k] = round(metrics[k] - prev_metrics[k], 6)
        delta["score"] = round(compute_score(metrics) - compute_score(prev_metrics), 6)
    return {
        "version": version,
        "change": change,
        "commit": commit,
        "instance": instance,
        "reference": reference,
        "config": config,
        "metrics": {k: (round(v, 6) if isinstance(v, float) else v)
                    for k, v in metrics.items()},
        "score": round(compute_score(metrics), 6),
        "delta": delta,
    }


def snapshots_to_json(snapshots: list, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(snapshots, fh, ensure_ascii=False, indent=2)
