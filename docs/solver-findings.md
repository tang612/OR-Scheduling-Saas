# CP-SAT / OR-Tools 版本与 API 发现

> 知识注入闭环记录：每次求解器版本变更 / API 存疑时更新，与版本号一一对应。

## ortools 9.15.6755（2026-08 本地验证）

### API 命名：双命名并存

| 事实 | 证据 |
|---|---|
| 官方源码主定义是 **snake_case**（`def new_optional_interval_var`、`def add_no_overlap`） | GitHub stable 分支 `ortools/sat/python/cp_model.py` |
| **camelCase 别名在实例上可用**（`NewOptionalIntervalVar`、`AddNoOverlap`、`AddExactlyOne`、`AddCumulative`） | 本地 `hasattr(CpModel(), name)` 全部 ✓；且 camelCase 调用运行成功（OPTIMAL） |
| camelCase 签名表现为 `(*args, **kwargs)`（动态转发），无法用 inspect 获取参数签名 | 本地 inspect 实测 |
| **`AddEndBeforeStart` 在 9.x 源码中不存在**（camelCase 与 snake_case 均无） | GitHub stable 源码 grep ✗；实例 hasattr ✗ |

### 结论与使用规范

1. **camelCase 教学命名可用**（官方文档与教程沿用），与 snake_case 等价——两种写法在 9.15 都能跑
2. **禁止使用 `AddEndBeforeStart`**（9.x 已移除/从未存在）——工序链用 `model.Add(end_prev <= start_next)` 或 `Add(s[k+1] >= e[k])` 实现
3. **存疑 API 的快速验证**：`python3 -c "from ortools.sat.python import cp_model; print(hasattr(cp_model.CpModel(), '方法名'))"`（注意：类属性为 snake_case，实例属性两者皆有，验证用**实例**）
4. 验证官方源码：`curl https://raw.githubusercontent.com/google/or-tools/stable/ortools/sat/python/cp_model.py | grep "def 方法名"`

### 序列相关切换时间（setup）建模发现（2026-08 排产任务验证）

| 事实 | 证据 |
|---|---|
| **`AddTransitionTime` 不存在**（9.15.6755） | 实例 `hasattr(CpModel(), "AddTransitionTime")` ✗ |
| `AddCircuit` / `AddMultipleCircuit` 存在 | 实例 hasattr ✓ |
| `AddNoOverlap` / `AddMaxEquality` / `AddAllowedAssignments` / `AddReservoirConstraint` 存在 | 实例 hasattr ✓ |

**结论**：CP-SAT 无原生 transition/setup API，序列相关切换时间必须用 `AddCircuit`（含虚拟 depot 节点）+ 弧 literal + `OnlyEnforceIf` 显式约束表达：

```python
# 弧 (i→k) 激活时施加 setup 约束
model.Add(S_k >= C_i + setup).OnlyEnforceIf(arc_lit[i, k])
# null 切换 = 不建弧（禁止紧邻，可经第三配方订单绕行）
```

### 版本变更速查

- 9.15：双命名并存确认；`AddEndBeforeStart` 缺失；`AddTransitionTime` 缺失（setup 用 AddCircuit 表达）
- （后续版本更新时在此追加对比记录）
