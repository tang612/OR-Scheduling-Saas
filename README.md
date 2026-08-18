# OR-Scheduling-Saas

> 手术排程 / 多机台智能排产算法 —— 用 Hermes Agent 从第一性原理到可运行交付

## 项目现状（截至 2026-08）

本项目已完成 **多机台智能排产算法** 的核心引擎与四层测试（L1~L4），L5 大规模压力测试待后续补充。当前交付的是**可运行、可验证、可追溯**的调度求解内核，后续可无缝接入 SaaS 平台。

| 阶段 | 状态 |
|------|------|
| 需求规格（V4 冻结版，10 项决策点确认） | ✅ 完成 |
| 数学模型（三目标加权和，公式 (1)~(7)） | ✅ 完成 |
| 第一性原理 + 反幻觉审查（修正 3 处错误断言） | ✅ 完成 |
| 算法核心代码（CP-SAT + 构造启发式 + ALNS） | ✅ 完成 |
| 四层测试 L1~L4（含性能数据 + 自动约束验证） | ✅ 完成 |
| L5 massive 极限压力测试 | ⏳ 待补 |

---

## 问题定义（需求 V4 冻结版）

- **范式**：并行机调度 + 序列相关切换时间 + 机器-配方兼容性，复杂度**强 NP-难**
- **订单**：不可拆分（整单 = 数量 × 单件加工时间），交期为软约束
- **切换时间**：对角 = 同配方清理，非对角 = 跨配方切换，均叠加机台 cleanup_time；`null` = 不可直接切换（可经中间配方绕行）
- **三目标（均无权重）**：`min λ1·C_max + λ2·ΣT_j + λ3·ΣC_j`，λ 由用户定义，默认 `(0,1,0)`
- **原则**：性能优先，数据决定模型（按规模自动路由求解器）

## 求解器路由（数据决定模型）

| 规模 | 求解器 | 验收 |
|------|--------|------|
| n ≤ 20（L1/L2） | CP-SAT 精确 | 证明最优 |
| n ≤ 80（L3） | 构造 + ALNS 300s | 5 分钟内出解 |
| n ≤ 300（L4） | 构造 + ALNS 900s | 15 分钟内出解 |
| n > 300（L5） | 构造 + ALNS 900s | 可用解 |

> 实测依据：序列相关切换 + tardiness 目标下，ALNS 60s（ΣT=7280）优于 CP-SAT 300s（ΣT=7828），故 L3 采用元启发。

---

## 四层测试结果（性能数据）

| 层级 | 规模 | 状态 | 求解器 | makespan | ΣT | 耗时 | 验证 |
|------|------|------|--------|----------|-----|------|------|
| L1 toy | 3机×5单 | OPTIMAL | CP-SAT | 90 | 82 | 0.01s | ✓ 下界=解值 |
| L2 boundary | 4机×12单(8 null) | OPTIMAL | CP-SAT | 570 | 1270 | 24.7s | ✓ null 正确处理 |
| L3 medium | 8机×50单 | FEASIBLE | 构造+ALNS | 933 | 7292 | 300s | ✓ 约束通过 |
| L4 large | 20机×200单 | FEASIBLE | 构造+ALNS | 2120 | 53169 | 900s | ✓ 30万次迭代 |

详见 `docs/test-reports/`（L1~L4 报告 + 汇总）。

---

## 目录结构

```
OR-Scheduling-Saas/
├── scripts/
│   ├── scheduler/          # 算法核心包
│   │   ├── model.py        # 数据模型 + 加载 + 体检 + 预检 + 评估
│   │   ├── cp_sat.py       # CP-SAT 精确求解（circuit 表达序列相关切换）
│   │   ├── heuristics.py   # 构造启发式（EDD/SPT/LPT）+ ALNS
│   │   ├── router.py       # 求解器路由（数据决定模型）
│   │   └── visualize.py    # 分层可视化（负载图/热力图/延误散点/甘特图）
│   ├── run_scheduler.py    # CLI 单层求解
│   └── run_tests.py        # L1-L4 测试 + 约束验证
├── tests/unit/             # 单元测试
├── docs/
│   ├── personality/        # Personality 最终版
│   ├── test-reports/       # 四层测试报告
│   ├── bootstrap-log.md    # 自举迭代日志
│   └── anti-hallucination-checklist.md  # 反幻觉核对清单
└── skills/                 # 三条流水线 Skill
```

---

## 快速开始

```bash
# 依赖：Python 3.9+，ortools 9.15（已实机验证 API）
pip install ortools

# 求解单层数据（默认 λ=(0,1,0) = tardiness 单目标）
python scripts/run_scheduler.py <数据目录> --lambda 0,1,0

# 运行四层测试
python scripts/run_tests.py --levels toy,boundary,medium,large

# 运行单元测试
python -m pytest tests/unit/ -v
```

输入数据为 5 个 JSON（machines / orders / recipes / switch_matrix / metadata），格式见 `mip_course/data/{toy,boundary,medium,large,massive}`。

---

## 项目文档导航

| 文档 | 路径 | 说明 |
|------|------|------|
| Personality 最终版 | `docs/personality/运筹优化工程师-V3.0.md` | 运筹优化工程师人格（V3.0，含反幻觉红线） |
| Agent 人格自举迭代日志 | `docs/bootstrap-log.md` | 人格 V2.1→V3.2 自举迭代史 + 本项目增量 |
| 反幻觉核对清单 | `docs/anti-hallucination-checklist.md` | 三步制 + 红线 + 六维校验 |
| 三条流水线 Skill | `skills/{app-dev-flow,change-request,debug}/SKILL.md` | 开发/变更/调试流程 |
| 四层测试报告 | `docs/test-reports/` | L1~L4 报告 + 汇总 |

---

## 开发方法论

本项目遵循三条流水线 + 反幻觉纪律：

- **app-dev-flow**：文档 → 门禁 → 开发 → 测试 → 审查 → 记录（每阶段停等确认）
- **change-request**：文档永远是单一事实来源，先改文档后改代码
- **debug**：理解问题 → 定位根因 → 修复 → 验证（禁止边改边试探）
- **反幻觉**：公式门禁 → 编号映射 → 逐行对照表；API 实机验证（不凭记忆）

核心铁律：**公式先行，没有 LaTeX 公式就没有一行代码**。

---

## 许可证

内部项目，版权所有。
