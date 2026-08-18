"""数据模型、加载、体检、可行性预检、调度评估。

公式编号对应需求 V4 模型 (1)~(7)。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Optional


class DataError(Exception):
    """数据加载/校验错误，携带错误码与中文诊断。"""

    def __init__(self, code: str, msg: str):
        self.code = code
        self.msg = msg
        super().__init__(f"[{code}] {msg}")


@dataclass
class Machine:
    id: str
    name: str
    allowed_recipes: set
    cleanup_time: int


@dataclass
class Order:
    id: str
    recipe_id: str
    quantity: int
    due_time: int
    priority: int  # 忽略（D1），仅输出展示


@dataclass
class DataModel:
    """订单不可拆分、机器-配方兼容、序列相关切换（对角=清理/非对角=切换/null=禁止）。"""

    machines: list
    orders: list
    recipes: dict                  # recipe_id -> processing_time
    switch: dict                   # (recipe_u, recipe_v) -> int | None
    recipe_index: dict             # recipe_id -> 矩阵索引

    # 派生量（整数时间单位，Q9）
    p: list = field(default_factory=list)        # p[j] 订单加工时间
    d: list = field(default_factory=list)        # d[j] 交期
    rho: list = field(default_factory=list)      # rho[j] 订单配方 id
    compatible: list = field(default_factory=list)  # compatible[j][m]
    max_switch: int = 0                          # 非 null 切换值上界
    max_cleanup: int = 0

    @property
    def n(self) -> int:
        return len(self.orders)

    @property
    def m(self) -> int:
        return len(self.machines)

    def horizon_ub(self) -> int:
        """E3: Σp_j + (n-1)·max_s，max_s = 非 null 切换上界 + cleanup 上界。"""
        if self.n == 0:
            return 0
        max_s = self.max_switch + self.max_cleanup
        return sum(self.p) + (self.n - 1) * max_s


# ---------------------------------------------------------------------------
# 加载与体检
# ---------------------------------------------------------------------------

def load_data(data_dir: str) -> DataModel:
    """读取 5 个 JSON，做字段校验与派生量构建。"""
    def _read(name: str):
        path = os.path.join(data_dir, name)
        if not os.path.exists(path):
            raise DataError("ERR_MISSING_FILE", f"缺少文件 {name}")
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except json.JSONDecodeError as e:
            raise DataError("ERR_BAD_JSON", f"JSON 解析失败 {name}: {e}")

    machines_raw = _read("machines.json")
    orders_raw = _read("orders.json")
    recipes_raw = _read("recipes.json")
    switch_raw = _read("switch_matrix.json")

    # 空输入检测（L3）
    if not machines_raw:
        raise DataError("ERR_EMPTY_MACHINES", "机台列表为空")
    if not orders_raw:
        raise DataError("ERR_EMPTY_ORDERS", "订单列表为空")
    if not recipes_raw:
        raise DataError("ERR_EMPTY_RECIPES", "配方列表为空")

    # recipes
    recipes = {}
    for r in recipes_raw:
        if "id" not in r or "processing_time" not in r:
            raise DataError("ERR_FIELD_MISSING", f"配方缺字段 id/processing_time: {r}")
        recipes[r["id"]] = r["processing_time"]

    # machines
    machines = []
    for m in machines_raw:
        for f in ("id", "allowed_recipes", "cleanup_time"):
            if f not in m:
                raise DataError("ERR_FIELD_MISSING", f"机台缺字段 {f}: {m}")
        machines.append(Machine(
            id=m["id"], name=m.get("name", m["id"]),
            allowed_recipes=set(m["allowed_recipes"]),
            cleanup_time=int(m["cleanup_time"]),
        ))

    # orders（priority 可缺省，忽略）
    orders = []
    for o in orders_raw:
        for f in ("id", "recipe_id", "quantity", "due_time"):
            if f not in o:
                raise DataError("ERR_FIELD_MISSING", f"订单缺字段 {f}: {o}")
        if o["recipe_id"] not in recipes:
            raise DataError("ERR_UNKNOWN_RECIPE", f"订单 {o['id']} 配方 {o['recipe_id']} 未定义")
        orders.append(Order(
            id=o["id"], recipe_id=o["recipe_id"],
            quantity=int(o["quantity"]), due_time=int(o["due_time"]),
            priority=int(o.get("priority", 0)),
        ))

    # switch_matrix
    if "recipes" not in switch_raw or "matrix" not in switch_raw:
        raise DataError("ERR_FIELD_MISSING", "switch_matrix 缺 recipes/matrix")
    sw_recipes = list(switch_raw["recipes"])
    recipe_index = {r: i for i, r in enumerate(sw_recipes)}
    matrix = switch_raw["matrix"]
    switch = {}
    for i, u in enumerate(sw_recipes):
        for j, v in enumerate(sw_recipes):
            val = matrix[i][j]
            switch[(u, v)] = None if val is None else int(val)

    # 派生量
    p = [o.quantity * recipes[o.recipe_id] for o in orders]
    d = [o.due_time for o in orders]
    rho = [o.recipe_id for o in orders]
    compatible = [[o.recipe_id in m.allowed_recipes for m in machines] for o in orders]
    max_switch = max((s for s in switch.values() if s is not None), default=0)
    max_cleanup = max((m.cleanup_time for m in machines), default=0)

    return DataModel(
        machines=machines, orders=orders, recipes=recipes, switch=switch,
        recipe_index=recipe_index, p=p, d=d, rho=rho, compatible=compatible,
        max_switch=max_switch, max_cleanup=max_cleanup,
    )


def feasibility_check(data: DataModel) -> None:
    """L2/L3 可行性预检：全冲突检测 + null 孤岛警告。不可行则抛 DataError。"""
    # 4.1 全冲突（L3）：每订单至少一台合格机台
    for j in range(data.n):
        if not any(data.compatible[j]):
            raise DataError(
                "ERR_INFEASIBLE",
                f"订单 {data.orders[j].id} 配方 {data.rho[j]} 无任何可用机台",
            )

    # 4.2 null 切换孤岛检测（L2）：每台机器 allowed 配方间的连通性
    for mm, m in enumerate(data.machines):
        allowed = sorted(m.allowed_recipes)
        if len(allowed) <= 1:
            continue
        # 建无向图：u-v 有边当 s[u][v] 或 s[v][u] 非 null
        adj = {r: set() for r in allowed}
        for u in allowed:
            for v in allowed:
                if u == v:
                    continue
                if data.switch.get((u, v)) is not None or data.switch.get((v, u)) is not None:
                    adj[u].add(v)
                    adj[v].add(u)
        # BFS 连通分量
        seen = set()
        comps = []
        for r in allowed:
            if r in seen:
                continue
            stack = [r]
            seen.add(r)
            comp = {r}
            while stack:
                cur = stack.pop()
                for nb in adj[cur]:
                    if nb not in seen:
                        seen.add(nb)
                        comp.add(nb)
                        stack.append(nb)
            comps.append(comp)
        if len(comps) > 1:
            # 孤岛存在：该机台无法在多个配方间自由切换，仅作警告（分配时可能被迫单配方）
            islands = ",".join(sorted(c) for c in comps)
            print(f"  [警告] 机台 {m.id} 存在切换孤岛: {islands}")


# ---------------------------------------------------------------------------
# 调度评估
# ---------------------------------------------------------------------------

@dataclass
class Schedule:
    """一个完整调度解：机台分配 + 每机台订单序列（按加工顺序）。"""
    assignment: list          # assignment[j] = 机台 index
    sequences: list           # sequences[m] = [订单 j, ...] 按加工顺序
    start: list = field(default_factory=list)   # start[j]
    end: list = field(default_factory=list)     # end[j]
    makespan: int = 0
    tardiness: int = 0        # Σ max(0, C_j - d_j)（无权重，D1）
    completion: int = 0       # Σ C_j（无权重，C1）
    feasible: bool = True
    infeasible_reason: str = ""


def evaluate(data: DataModel, assignment: list, sequences: list,
             lambda_: tuple = (0.0, 1.0, 0.0)) -> Schedule:
    """按分配与序列计算起止时刻、目标分量。null 切换视为不可行（返回 feasible=False）。"""
    n, m = data.n, data.m
    start = [0] * n
    end = [0] * n
    feasible = True
    reason = ""

    for mm in range(m):
        t = 0
        last_recipe = None
        for j in sequences[mm]:
            setup = 0
            if last_recipe is not None:
                s_val = data.switch.get((last_recipe, data.rho[j]))
                if s_val is None:
                    feasible = False
                    reason = (f"机台 {data.machines[mm].id} 上配方 "
                              f"{last_recipe}→{data.rho[j]} 不可切换（null）")
                    break
                setup = s_val + data.machines[mm].cleanup_time
            start[j] = t + setup
            end[j] = start[j] + data.p[j]
            t = end[j]
            last_recipe = data.rho[j]
        if not feasible:
            break

    if feasible:
        makespan = max(end) if n > 0 else 0
        tardiness = sum(max(0, end[j] - data.d[j]) for j in range(n))
        completion = sum(end[j] for j in range(n))
    else:
        makespan = tardiness = completion = 10 ** 9

    obj = (lambda_[0] * makespan + lambda_[1] * tardiness
           + lambda_[2] * completion)
    return Schedule(
        assignment=assignment, sequences=sequences, start=start, end=end,
        makespan=makespan, tardiness=tardiness, completion=completion,
        feasible=feasible, infeasible_reason=reason,
    )
