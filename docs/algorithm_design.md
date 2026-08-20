# 多机台智能排产算法 · 最终版代码方案（第一性原理审查后）

> 阶段一 · 最终冻结版：整合需求 V4、代码逻辑、可视化方案，并经第一性原理 + 反幻觉清单审查修正。
> 本文档不含求解代码，仅定义最终算法方案，作为阶段二编码的唯一事实来源。

---

## 0. 第一性原理审查结论（反幻觉清单核对）

以下为审查中**发现并修正的错误断言**与**确认的关键事实**，防止幻觉传导至编码阶段。

### 已修正的错误（防幻觉）

| # | 原断言（错误） | 第一性原理事实（修正后） | 影响 |
|---|---|---|---|
| E1 | 无 setup 时 P_m‖ΣC_j 已强 NP-难 | **P_m‖ΣC_j 多项式可解**（SPT 列表调度最优，Smith 1956）；NP-难来自 ΣT_j 与序列相关 setup | 复杂度判定依据纠正 |
| E2 | 单机 1‖ΣT 下 EDD 最优 | **EDD 是 1‖L_max 最优**（Jackson 1955）；**1‖ΣT_j 是 NP-难**（Du & Leung 1990），EDD 仅是启发式 | L2 单机测试的解析验证基准修正 |
| E3 | horizon = Σp_j + max_setup×(n+m) | 收紧为 **Σp_j + (n−1)×max_s**（订单序列长度 = n，切换次数 ≤ n−1；max_s = 非 null 切换+cleanup 上界） | 数值卫生：Big-M 收紧 |

### 已确认的正确事实（反幻觉）

| # | 事实 | 证据 |
|---|---|---|
| F1 | **`AddTransitionTime` 不存在**（ortools 9.15.6755） | 本地 `hasattr` ✗ |
| F2 | `AddCircuit`/`AddMultipleCircuit`/`AddNoOverlap`/`AddMaxEquality` 存在 | 本地 `hasattr` ✓ |
| F3 | 序列相关 setup 用 **AddCircuit + 弧 literal + OnlyEnforceIf** 表达 | 落库 `docs/solver-findings.md` |
| F4 | SPT 最优：1‖ΣC_j、P_m‖ΣC_j；WSPT 最优：1‖Σw_jC_j | 调度理论经典结论 |
| F5 | LPT 是 P‖C_max 的 (4/3 − 1/(3m)) 近似（Graham 1969） | 调度理论经典结论 |
| F6 | load_factor = 纯加工量 / 容量，**不含 setup+cleanup**（实际负载更高） | toy 200/360=0.56 等五层逐一验证吻合 |

### 补充洞察（第一性原理推导）

1. **null 绕行语义精确化**：s[ρ_i][ρ_k]=null 仅禁止「配方 i 订单之后紧接配方 k 订单」，绕行 = 中间插入第三配方订单；订单序列长度恒为 n，故切换次数仍 ≤ n−1。
2. **单机退化（L2 单机台）分目标验证**：λ3 目标（ΣC_j）→ SPT 解析最优；λ2 目标（ΣT_j）→ NP-难，需精确求解交叉验证（EDD 仅启发式）；λ1 目标（C_max）→ 单机 makespan 仅受切换顺序影响（退化为单机 TSP）。
3. **实际负载 > load_factor**：L2~L5 的 load_factor 已 1.69~1.89，叠加 setup+cleanup 后过载更严重，tardiness 目标权重更高。

---

## 1. 最终复杂度判定

问题 P_m | M_j, s_uv | λ1·C_max + λ2·ΣT_j + λ3·ΣC_j：

| 目标分量 | 无 setup | 带序列相关 setup（本问题） |
|---|---|---|
| C_max | NP-难（3 机起） | NP-难（单机退化为 TSP） |
| ΣT_j | **强 NP-难**（1 机已 NP-难） | 强 NP-难 |
| ΣC_j | **多项式**（SPT） | NP-难（单机退化为 TSP） |

**整体：强 NP-难**（因 ΣT_j 目标与序列相关 setup 双重 NP-难来源）。→ 精确求解仅 L1~L3 可行，L4/L5 必须元启发。

---

## 2. 总体架构与数据流

```
输入 5 JSON → [1]数据体检 → [2]可行性预检 → [3]求解器路由
                                            ├─ L1/L2: CP-SAT 精确
                                            ├─ L3:    CP-SAT 时间限 300s
                                            ├─ L4:    构造 + CP-SAT 初解 + ALNS
                                            └─ L5:    构造 + ALNS/禁忌
                                            → [4]分层可视化 + 核对清单
```

---

## 3. 模块一：数据加载与体检（L3 空输入鲁棒性）

```text
load_and_validate(path):
    try 读 machines/orders/recipes/switch_matrix
    catch 缺文件/坏 JSON → Error(code, 中文诊断)
    空机台/空订单/空配方 → Error("ERR_EMPTY_*")        # L3
    字段缺失 → Error("ERR_FIELD_MISSING")
    构建: p_j = quantity_j × processing_time(ρ_j)
          s[u][v] = matrix[u][v]  (null → None=不可切换)
```

---

## 4. 模块二：可行性预检（L2 高 null / L3 全冲突）

```text
feasibility_check(data):
    # 4.1 全冲突检测（L3）
    for j: 若 recipe_j 无任何机台允许 → INFEASIBLE("订单 j 无可用机台")

    # 4.2 null 切换孤岛检测（L2）
    for m in machines:
        # 配方图: 节点=allowed_recipes, 边=s[u][v]!=null
        # 若存在孤立配方（无法经合法切换到达其他配方）
        #   → 该机台只能单配方使用，多配方订单共存时潜在不可行 → 警告

    # 4.3 求解后 INFEASIBLE → IIS 定位最小矛盾集，禁止盲删约束
```

---

## 5. 模块三：求解器路由（数据决定模型）

```text
route(data, λ, budget):
    n = len(orders)
    n ≤ 20   → CP-SAT 精确(time_limit=∞)            # L1(5) L2(12)
    n ≤ 80   → 构造 + ALNS 300s                      # L3(50)
    n ≤ 300  → 构造 + ALNS 900s                      # L4(200)
    else     → 构造 + ALNS 900s                      # L5(500)
```

**实测依据（反幻觉，2026-08 L3 medium 数据）**：CP-SAT 300s 得 ΣT=7828（gap 90%）；构造+ALNS 60s 得 ΣT=7280（优于 CP-SAT）。序列相关切换 + tardiness 目标下，CP-SAT 下界难收紧，元启发更快更优。故 L3 由「CP-SAT 时间限」改为「元启发」。

---

## 6. 模块四：CP-SAT 精确建模（L1~L3，L4 初解）

```text
cp_sat_solve(data, λ, time_limit):
    horizon = Σp_j + (n-1) × max_s          # E3 收紧后的上界
    # max_s = max(非 null 切换值) + max(cleanup)

    for j, m where ρ_j ∈ m.allowed:         # (3) 兼容
        x[j,m] = BoolVar
        iv[j,m] = OptionalIntervalVar(s[j,m], p_j, s[j,m]+p_j, x[j,m])
    for j: Add(Σ_m x[j,m] == 1)             # (2)
    for m: AddNoOverlap([iv[j,m]])          # (4)

    for m:                                   # (5) 切换 + null（F3: circuit 方案）
        arcs = []
        for (i,k) where s[ρ_i][ρ_k] != null:   # null 弧不建 → 禁止紧邻
            lit[i,k] = BoolVar()
            arcs.append((i, k, lit[i,k]))
            Add(S_k >= S_i + p_i + s[ρ_i][ρ_k] + cleanup_m).OnlyEnforceIf(lit[i,k])
        AddCircuit(arcs + 虚拟 depot 弧)     # 每机台订单成单链

    for j: AddMaxEquality(T[j], [C_j - d_j, 0])   # (6)
    AddMaxEquality(Cmax, [C_j])                   # (7)
    Minimize(λ1·Cmax + λ2·ΣT_j + λ3·ΣC_j)        # (1)
    solver.max_time = time_limit
    Solve()
```

**已确定（无待验证项）**：AddTransitionTime 不存在，circuit + OnlyEnforceIf 是唯一正解；AddCircuit/AddMaxEquality 已验证存在。

---

## 7. 模块五：构造启发式（L4/L5 初解）

```text
constructive_heuristic(data, λ):
    # 排序键（F4/F5 修正后的理论锚点）
    if λ2 主导: key = d_j          # EDD（L_max 最优；对 ΣT 是启发式）
    elif λ3 主导: key = p_j        # SPT（P_m||ΣC_j 最优）
    elif λ1 主导: key = -p_j       # LPT（P||C_max 的 4/3-1/3m 近似）

    列表调度: 按 key 排序，依次插入最早可完成机台
    setup = s[上配方][ρ_j] + cleanup_m（null → +∞ 不可选）
```

**理论锚点（修正后）**：
- SPT → 1‖ΣC_j、P_m‖ΣC_j 最优（L2 单机 + λ3 可解析验证）
- EDD → 1‖L_max 最优（对 ΣT_j 非最优，仅启发式）
- LPT → P‖C_max 的 4/3−1/(3m) 近似
- 1‖ΣT_j 无简单解析最优（NP-难），L2 单机 + λ2 需精确交叉验证

---

## 8. 模块六：元启发（ALNS + 禁忌，L4/L5 主力）

```text
alns(data, s0, time_limit, λ):
    s = s_best = s0; T = 初始温度; weights = 均匀
    while 未超时:
        destroy = 轮盘赌(破坏算子); repair = 轮盘赌(修复算子)
        s_new = repair(destroy(s, k))
        if Δ<0 or exp(-Δ/T) > random(): s = s_new
        if f(s) < f(s_best): s_best = s
        update_weights(改进量); T *= cooling
    return s_best
```

- 破坏算子：随机 / 最坏（延误大者）/ 相关（同配方成组）
- 修复算子：贪婪插入 / regret-k / 配方分块插入
- 可选局部搜索：机台内 2-opt / 机台间移动 / 配方分块

**质量基准（反幻觉红线）**：启发式交付必须附 L1~L3 小规模实例对比精确解的 gap，禁止隐瞒质量差距。

---

## 9. 模块七：多目标评估（λ 接口）

```text
evaluate(schedule, λ) = λ1·Cmax + λ2·Σ max(0, C_j - d_j) + λ3·Σ C_j
# 三目标均无权重（D1 忽略 priority）；默认 λ=(0,1,0)；支持字典序扩展
```

---

## 10. 模块八：混合求解（L4）

```text
hybrid(data, λ, 900s):
    s0   = constructive_heuristic()          # 秒级
    s_cp = cp_sat_solve(60s, warm_start=s0)  # CP-SAT 短时
    s    = alns(s_cp or s0, 剩余时间)
    return s
```

---

## 11. 各层方法对应表（最终）

| 层级 | 规模 | 方法 | 验收 |
|------|------|------|------|
| L1 toy | 5 单 | CP-SAT 精确 | 正确解 + 手工验证 |
| L2 boundary | 12 单（8 null） | CP-SAT 精确 + null 预检 | 高 null 比例不崩溃 |
| L3 medium | 50 单 | CP-SAT 时间限 300s | 5 分钟内出解 |
| L4 large | 200 单 | 构造 + CP-SAT warmstart + ALNS | 15 分钟内出解 |
| L5 massive | 500 单 | 构造 + ALNS/禁忌 | 可用解 + 质量报告 |

---

## 12. 可视化方案（V1~V3 已确认，并入）

甘特图仅用于 L1/L2 手工验证与瓶颈下钻；大规模采用分层可视化（详见 `docs/visualization_design.md`）：

| 层级 | 主视图 | 辅助 |
|------|--------|------|
| L1/L2 | 甘特图（手工验证） | KPI / 切换统计 |
| L3 | 负载图 + 延误散点 | 简化甘特图 |
| L4/L5 | 负载堆叠图 + 时间热力图 + 延误散点 + KPI | 瓶颈甘特图下钻 + 收敛曲线 |

- 技术：matplotlib（静态嵌入报告）+ plotly（L4/L5 交互 HTML）
- 默认不生成全量甘特图（L4/L5），仅 Top-K 瓶颈甘特图（V3）

---

## 13. 编码前待验证清单（已收窄）

1. ~~AddTransitionTime 是否存在~~ → **已确认不存在**，circuit 方案定稿（落库 solver-findings.md）
2. AddCircuit 的虚拟 depot 节点语义与 null 弧在 L2 boundary（8 null）下的正确性（编码时验证）
3. ALNS 参数（k/tenure/温度/冷却率）在 L4/L5 的敏感性调优
4. 启发式质量基准：L1~L3 小规模实例 gap 统计（反幻觉红线）
