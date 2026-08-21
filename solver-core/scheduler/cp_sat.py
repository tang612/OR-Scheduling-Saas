"""CP-SAT 精确求解器：optional interval + NoOverlap + circuit 表达序列相关切换。

公式编号对应需求 V4 模型 (1)~(7)。
- (2) 每订单恰一机台  (3) 机器-配方兼容  (4) NoOverlap
- (5) 切换+清理（circuit + OnlyEnforceIf，null 不建弧）  (6) 延误  (7) makespan
"""
from __future__ import annotations

import time
from ortools.sat.python import cp_model

from .model import DataModel, evaluate


def _thin(points: list, cap: int = 500):
    """等间隔抽稀（保留首尾），防止超长轨迹撑爆前端渲染。"""
    if len(points) <= cap:
        return points
    step = len(points) / cap
    out = [points[int(i * step)] for i in range(cap - 1)]
    out.append(points[-1])
    return out


def _solve_cp_sat(data: DataModel, lambda_: tuple, time_limit: float | None,
                  progress_cb=None, cancel=None, log_cb=None):
    """构建并求解 CP-SAT 模型，返回 (status, Schedule, objective, gap, wall, trace)。

    trace = {convergence: [(t, obj, bound)], logs: [...], termination, params}，
    供 Dashboard 求解日志面板 / 收敛曲线 / 参数回显使用。
    """
    model = cp_model.CpModel()
    n, m = data.n, data.m
    horizon = max(1, data.horizon_ub())

    # ---- 决策变量：optional interval ----
    start = {}     # (j, mm) -> IntVar
    end = {}       # (j, mm) -> IntVar
    presence = {}  # (j, mm) -> BoolVar
    interval = {}  # (j, mm) -> IntervalVar

    for j in range(n):
        for mm in range(m):
            if data.compatible[j][mm]:
                s = model.NewIntVar(0, horizon, f"s_{j}_{mm}")
                e = model.NewIntVar(0, horizon, f"e_{j}_{mm}")
                model.Add(e == s + data.p[j])                      # 不可中断（定义式）
                x = model.NewBoolVar(f"x_{j}_{mm}")
                iv = model.NewOptionalIntervalVar(s, data.p[j], e, x, f"iv_{j}_{mm}")
                start[(j, mm)], end[(j, mm)] = s, e
                presence[(j, mm)] = x
                interval[(j, mm)] = iv

    # ---- (2) 每订单恰一台机台 ----
    for j in range(n):
        model.AddExactlyOne([presence[(j, mm)] for mm in range(m)
                             if data.compatible[j][mm]])

    # ---- (4) 每机台 NoOverlap ----
    for mm in range(m):
        ivs = [interval[(j, mm)] for j in range(n) if data.compatible[j][mm]]
        if ivs:
            model.AddNoOverlap(ivs)

    # ---- (5) circuit + 序列相关切换 + null ----
    # 节点索引：每机台一个 depot，每个合格 (j,mm) 一个订单节点
    node = {}
    idx = 0
    for mm in range(m):
        node[("depot", mm)] = idx
        idx += 1
        for j in range(n):
            if data.compatible[j][mm]:
                node[(j, mm)] = idx
                idx += 1

    for mm in range(m):
        depot = node[("depot", mm)]
        arcs = []
        for j in range(n):
            if not data.compatible[j][mm]:
                continue
            nj = node[(j, mm)]
            # depot -> j（第一单无切换） 与 j -> depot（最后一单无清理）
            arcs.append((depot, nj, model.NewBoolVar(f"depot_{mm}_to_{j}")))
            arcs.append((nj, depot, model.NewBoolVar(f"{j}_to_depot_{mm}")))
            # 自环：订单 j 不在该机台时，节点不参与回路
            arcs.append((nj, nj, presence[(j, mm)].Not()))

        # 订单间弧：仅非 null 配方对
        for j in range(n):
            if not data.compatible[j][mm]:
                continue
            for k in range(n):
                if j == k or not data.compatible[k][mm]:
                    continue
                s_val = data.switch.get((data.rho[j], data.rho[k]))
                if s_val is None:
                    continue                          # null → 不建弧（禁止紧邻，可绕行）
                lit = model.NewBoolVar(f"arc_{mm}_{j}_{k}")
                arcs.append((node[(j, mm)], node[(k, mm)], lit))
                # 切换 + 清理（叠加）
                model.Add(end[(j, mm)] + s_val + data.machines[mm].cleanup_time
                          <= start[(k, mm)]).OnlyEnforceIf(lit)
        model.AddCircuit(arcs)

    # ---- (6) 延误 + (7) makespan（经每订单完工 C_j 统一） ----
    C = {}   # C[j] 订单完工
    T = {}   # T[j] 延误
    for j in range(n):
        C[j] = model.NewIntVar(0, horizon, f"C_{j}")
        for mm in range(m):
            if data.compatible[j][mm]:
                model.Add(C[j] == end[(j, mm)]).OnlyEnforceIf(presence[(j, mm)])
        T[j] = model.NewIntVar(0, horizon, f"T_{j}")
        model.Add(T[j] >= C[j] - data.d[j])      # (6) T_j >= C_j - d_j
        model.Add(T[j] >= 0)

    Cmax = model.NewIntVar(0, horizon, "Cmax")
    model.AddMaxEquality(Cmax, [C[j] for j in range(n)])   # (7) Cmax = max C_j

    # ---- (1) 目标：λ 加权和 ----
    obj = (lambda_[0] * Cmax
           + lambda_[1] * sum(T[j] for j in range(n))
           + lambda_[2] * sum(C[j] for j in range(n)))
    model.Minimize(obj)

    solver = cp_model.CpSolver()
    if time_limit is not None:
        solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 8
    solver.parameters.log_search_progress = True   # Dashboard 求解日志面板数据源

    # 日志采集：环形上限 10000 行（防大模型日志爆炸）；log_cb 用于实时流式推送（SSE）
    MAX_LOG_LINES = 10000
    log_lines: list[str] = []

    def _log(line: str) -> None:
        line = line.rstrip()
        if not line:
            return
        if len(log_lines) < MAX_LOG_LINES:
            log_lines.append(line)
        if log_cb is not None:
            log_cb(line)

    solver.log_callback = _log

    if progress_cb:
        progress_cb(0.3, "CP-SAT求解")
    t0 = time.time()

    # 统一带 SolutionCallback：收集收敛轨迹（首次可行解/最优解更新时间、bound 下降）
    trace_pts: list[tuple] = []   # (walltime, objective, bound)
    cancelled = False

    class _TraceCb(cp_model.CpSolverSolutionCallback):
        def __init__(self, fn):
            super().__init__()
            self._fn = fn
            self.cancelled = False

        def on_solution_callback(self):
            trace_pts.append((self.WallTime(), self.ObjectiveValue(),
                              self.BestObjectiveBound()))
            if self._fn is not None and self._fn():
                self.cancelled = True
                self.StopSearch()

    cb = _TraceCb(cancel)
    status = solver.Solve(model, cb)
    cancelled = cb.cancelled
    wall = time.time() - t0

    # 终止原因 + 参数回显（Dashboard 参数详情页）
    if status == cp_model.OPTIMAL:
        termination = "optimal"
    elif status == cp_model.FEASIBLE:
        termination = "cancelled" if cancelled else "time_limit"
    elif status == cp_model.INFEASIBLE:
        termination = "infeasible"
    else:
        termination = "unknown"
    params = {"engine": "CP-SAT", "time_limit_s": time_limit, "num_workers": 8,
              "log_search_progress": True}

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return status, None, None, None, wall, {
            "convergence": [], "logs": log_lines, "termination": termination,
            "params": params,
        }

    # 提取解
    assignment = [0] * n
    start_val = [0] * n
    end_val = [0] * n
    for j in range(n):
        for mm in range(m):
            if data.compatible[j][mm] and solver.Value(presence[(j, mm)]) == 1:
                assignment[j] = mm
                start_val[j] = solver.Value(start[(j, mm)])
                end_val[j] = solver.Value(end[(j, mm)])
                break

    # 重建每机台序列（按开工时间排序）
    sequences = [[] for _ in range(m)]
    for mm in range(m):
        seq = [(j, start_val[j]) for j in range(n) if assignment[j] == mm]
        seq.sort(key=lambda x: x[1])
        sequences[mm] = [j for j, _ in seq]

    sched = evaluate(data, assignment, sequences, lambda_)
    # 用求解器目标作为客观值（避免 evaluate 重建的浮点偏差）
    gap = None
    if status == cp_model.OPTIMAL:
        gap = 0.0
    else:
        best_bound = solver.BestObjectiveBound()
        obj_val = solver.ObjectiveValue()
        if obj_val > 0:
            gap = abs(obj_val - best_bound) / max(1.0, abs(obj_val))

    return status, sched, obj, gap, wall, {
        "convergence": [{"t": round(t, 3), "objective": round(o, 2), "bound": round(b, 2)}
                        for t, o, b in _thin(trace_pts)],
        "logs": log_lines,
        "termination": termination,
        "params": params,
    }


def solve(data: DataModel, lambda_: tuple, time_limit: float | None = None,
          verbose: bool = True, progress_cb=None, cancel=None,
          log_cb=None):
    """CP-SAT 精确求解入口。返回 dict。

    progress_cb(percent, stage)：进度回调（可选）。
    cancel() -> bool：取消检查（可选，返回 True 则软停止并返回当前最优解）。
    log_cb(line: str)：求解日志行回调（可选，实时流式）。
    """
    status, sched, obj_expr, gap, wall, trace = _solve_cp_sat(
        data, lambda_, time_limit, progress_cb, cancel, log_cb)
    status_name = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.UNKNOWN: "UNKNOWN",
        cp_model.MODEL_INVALID: "MODEL_INVALID",
    }.get(status, f"STATUS_{status}")

    if sched is None:
        return {
            "status": status_name, "schedule": None,
            "makespan": None, "tardiness": None, "completion": None,
            "objective": None, "gap": gap, "solve_time_s": wall,
            "convergence": trace["convergence"], "logs": trace["logs"],
            "termination": trace["termination"], "params": trace["params"],
        }

    if verbose:
        print(f"  [CP-SAT] status={status_name} makespan={sched.makespan} "
              f"ΣT={sched.tardiness} ΣC={sched.completion} "
              f"time={wall:.2f}s gap={gap}")

    return {
        "status": status_name,
        "schedule": sched,
        "makespan": sched.makespan,
        "tardiness": sched.tardiness,
        "completion": sched.completion,
        "objective": (lambda_[0] * sched.makespan + lambda_[1] * sched.tardiness
                      + lambda_[2] * sched.completion),
        "gap": gap, "solve_time_s": wall,
        "convergence": trace["convergence"], "logs": trace["logs"],
        "termination": trace["termination"], "params": trace["params"],
    }
