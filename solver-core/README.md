# solver-core

多机台智能排产求解核心，由 `scripts/scheduler` 包化而来（**算法逻辑零改动**，仅新增包配置）。

## 模块

| 模块 | 职责 | 第三方依赖 |
|---|---|---|
| `model.py` | 数据模型 / 加载体检 / 可行性预检 / 调度评估 | 无（标准库 + dataclass） |
| `cp_sat.py` | CP-SAT 精确求解（optional interval + NoOverlap + circuit 表达序列相关切换） | ortools |
| `heuristics.py` | 构造启发式（EDD/SPT/LPT）+ ALNS 元启发（增量评估） | 无（纯标准库） |
| `router.py` | 统一 `solve()` 入口，按规模自动路由 | 间接依赖 ortools |
| `evaluation.py` | 7 指标解质量评价 + 问题特定下界 | 无 |
| `visualize.py` | matplotlib 分层可视化（甘特图/负载/热力图） | matplotlib + numpy（可选） |

## 安装

```bash
pip install -e .          # 核心（仅 ortools 依赖）
pip install -e ".[viz]"   # 含可视化（matplotlib/numpy）
```

## 使用

```python
from scheduler.router import solve
from scheduler.model import load_data, feasibility_check

data = load_data("/path/to/data_dir")   # 含 5 个 JSON
feasibility_check(data)
result = solve(data, lambda_=(0.0, 1.0, 0.0), time_budget=300)
print(result["status"], result["objective"])
```

## 规模路由（`router.solve` 内建）

| 订单数 n | 策略 |
|---|---|
| n ≤ 20 | CP-SAT 精确 |
| n ≤ 80 | 构造 + ALNS 300s |
| n ≤ 300 | 构造 + ALNS 900s |
| else | 构造 + ALNS 900s |
