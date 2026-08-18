"""构造启发式（EDD/SPT/LPT 列表调度）与 ALNS 元启发（增量评估版）。

反幻觉锚点（第一性原理审查修正）：
- SPT 是 1||ΣC_j 与 P_m||ΣC_j 最优（Smith 1956）
- EDD 是 1||L_max 最优（Jackson 1955），对 ΣT_j 仅启发式
- LPT 是 P||C_max 的 (4/3-1/3m) 近似（Graham 1969）
"""
from __future__ import annotations

import math
import random
import time

from .model import DataModel, evaluate, Schedule


def constructive(data: DataModel, lambda_: tuple = (0.0, 1.0, 0.0),
                 seed: int = 0) -> Schedule:
    """列表调度：按 λ 主导目标排序，贪心插入最早可完成机台（含 null 延迟重试）。"""
    n, m = data.n, data.m

    if lambda_[1] > 0:                       # tardiness 主导 → EDD
        order = sorted(range(n), key=lambda j: data.d[j])
    elif lambda_[2] > 0:                     # completion 主导 → SPT
        order = sorted(range(n), key=lambda j: data.p[j])
    else:                                    # makespan 主导 → LPT
        order = sorted(range(n), key=lambda j: -data.p[j])

    assignment = [-1] * n
    sequences = [[] for _ in range(m)]
    metrics = [(0.0, 0.0, 0.0)] * m

    # 增量插入：尝试所有机台×所有位置（含中间插入，支持 null 绕行）
    for j in order:
        best = _insert_best(data, sequences, metrics, j, lambda_)
        if best is None:
            continue
        _, mm, pos, nm = best
        sequences[mm].insert(pos, j)
        assignment[j] = mm
        metrics[mm] = nm

    # 处理第一轮未放置订单（null 全阻延迟重试）
    for j in range(n):
        if assignment[j] != -1:
            continue
        best = _insert_best(data, sequences, metrics, j, lambda_)
        if best is None:
            return evaluate(data, assignment, sequences, lambda_)
        _, mm, pos, nm = best
        sequences[mm].insert(pos, j)
        assignment[j] = mm
        metrics[mm] = nm

    return evaluate(data, assignment, sequences, lambda_)


# ---------------------------------------------------------------------------
# ALNS（增量评估，副本式）
# ---------------------------------------------------------------------------

def _seq_metric(data: DataModel, seq: list, mm: int):
    """单机序列 metric = (end_time, tardiness, completion)。null 切换返回 None。"""
    t = 0.0
    tard = 0.0
    comp = 0.0
    last = None
    for j in seq:
        if last is not None:
            s = data.switch.get((last, data.rho[j]))
            if s is None:
                return None
            t += s + data.machines[mm].cleanup_time
        t += data.p[j]
        tard += max(0, t - data.d[j])
        comp += t
        last = data.rho[j]
    return (t, tard, comp)


def _global_obj(metrics, lambda_):
    mk = max((mt[0] for mt in metrics), default=0.0)
    tard = sum(mt[1] for mt in metrics)
    comp = sum(mt[2] for mt in metrics)
    return lambda_[0] * mk + lambda_[1] * tard + lambda_[2] * comp


def _order_end(data, sequences):
    """从序列重建每订单完工时间（供 worst 破坏算子用）。"""
    end = [0] * data.n
    for mm, seq in enumerate(sequences):
        t = 0.0
        last = None
        for j in seq:
            if last is not None:
                s = data.switch.get((last, data.rho[j]))
                t += (s if s is not None else 0) + data.machines[mm].cleanup_time
            t += data.p[j]
            end[j] = t
            last = data.rho[j]
    return end


def _insert_best(data, sequences, metrics, j, lambda_):
    """增量评估订单 j 的所有合法插入位置，返回 (mm, pos, new_metric) 或 None。"""
    m = data.m
    cur_mk = max((mt[0] for mt in metrics), default=0.0)
    cur_tard = sum(mt[1] for mt in metrics)
    cur_comp = sum(mt[2] for mt in metrics)
    cur_obj = lambda_[0] * cur_mk + lambda_[1] * cur_tard + lambda_[2] * cur_comp

    best = None
    for mm in range(m):
        if not data.compatible[j][mm]:
            continue
        seq = sequences[mm]
        old = metrics[mm]
        for pos in range(len(seq) + 1):
            new_seq = seq[:pos] + [j] + seq[pos:]
            nm = _seq_metric(data, new_seq, mm)
            if nm is None:
                continue
            delta_tard = nm[1] - old[1]
            delta_comp = nm[2] - old[2]
            delta_mk = max(0.0, nm[0] - cur_mk)
            delta = lambda_[0] * delta_mk + lambda_[1] * delta_tard \
                + lambda_[2] * delta_comp
            if best is None or delta < best[0]:
                best = (delta, mm, pos, nm)
    return best


def alns(data: DataModel, s0: Schedule, lambda_: tuple, time_limit: float,
         seed: int = 42, verbose: bool = True) -> Schedule:
    """自适应大邻域搜索 + 模拟退火（增量评估，副本式迭代）。"""
    rng = random.Random(seed)
    n, m = data.n, data.m

    sequences = [list(s) for s in s0.sequences]
    assignment = list(s0.assignment)
    metrics = []
    for mm in range(m):
        nm = _seq_metric(data, sequences[mm], mm)
        metrics.append(nm if nm is not None else (0.0, 0.0, 0.0))

    f_cur = _global_obj(metrics, lambda_)
    f_best = f_cur
    best_sequences = [list(s) for s in sequences]
    best_assignment = list(assignment)

    T = max(1.0, f_best * 0.02) if f_best > 0 else 1.0
    cooling = 0.9997

    d_weights = {"random": 1.0, "worst": 1.0}
    scores = {"random": 0.0, "worst": 0.0}
    counts = {"random": 0, "worst": 0}

    t0 = time.time()
    iteration = 0
    accepted = 0

    while time.time() - t0 < time_limit:
        iteration += 1
        frac = 1 - (time.time() - t0) / time_limit
        k = max(1, int(n * (0.04 + 0.20 * frac)))
        if k >= n:
            k = max(1, n - 1)

        d_name = _wheel(d_weights, rng)

        # 副本
        new_seq = [list(s) for s in sequences]
        new_assign = list(assignment)
        new_metrics = list(metrics)

        # 破坏
        order_end = _order_end(data, new_seq)
        removed = _destroy(data, order_end, d_name, k, rng)
        affected = set()
        for j in removed:
            mm = new_assign[j]
            if mm >= 0 and j in new_seq[mm]:
                new_seq[mm].remove(j)
                new_assign[j] = -1
                affected.add(mm)
        infeasible = False
        for mm in affected:
            nm = _seq_metric(data, new_seq[mm], mm)
            if nm is None:
                infeasible = True
                break
            new_metrics[mm] = nm
        if infeasible:
            continue

        # 修复（逐个插入）
        ok = True
        for j in removed:
            best = _insert_best(data, new_seq, new_metrics, j, lambda_)
            if best is None:
                ok = False
                break
            _, mm, pos, nm = best
            new_seq[mm].insert(pos, j)
            new_assign[j] = mm
            new_metrics[mm] = nm
        if not ok:
            continue

        # 接受准则
        f_new = _global_obj(new_metrics, lambda_)
        improved = f_new < f_best
        if f_new <= f_cur or rng.random() < math.exp(-(f_new - f_cur) / T):
            sequences, assignment, metrics = new_seq, new_assign, new_metrics
            f_cur = f_new
            accepted += 1
            if improved:
                f_best = f_new
                best_sequences = [list(s) for s in sequences]
                best_assignment = list(assignment)
                scores[d_name] += 1.0
        counts[d_name] += 1

        T *= cooling
        if iteration % 500 == 0:
            for name in ("random", "worst"):
                if counts[name] > 0:
                    d_weights[name] = max(0.1, d_weights[name] * 0.7
                                          + (scores[name] / counts[name]) * 3.0)
                scores[name] = 0.0
                counts[name] = 0

    best = evaluate(data, best_assignment, best_sequences, lambda_)
    if verbose:
        print(f"  [ALNS] iter={iteration} accepted={accepted} "
              f"makespan={best.makespan} ΣT={best.tardiness} ΣC={best.completion} "
              f"time={time.time()-t0:.2f}s")
    return best


def _wheel(weights, rng):
    total = sum(weights.values())
    r = rng.random() * total
    acc = 0.0
    for name, w in weights.items():
        acc += w
        if r <= acc:
            return name
    return list(weights.keys())[-1]


def _destroy(data, order_end, name, k, rng):
    n = data.n
    if name == "random":
        return rng.sample(range(n), k)
    tard = [max(0, order_end[j] - data.d[j]) for j in range(n)]
    idx = sorted(range(n), key=lambda j: -tard[j])
    return idx[:k]
