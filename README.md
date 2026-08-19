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
| 算法迭代优化（解质量评价体系 + 多指标引导 + 智能终止） | ✅ 完成 |
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

## 算法迭代优化（解质量评价体系 + 多指标引导 + 智能终止）

针对 L3 及以上大规模启发式调度，构建「评估 → 迭代优化」闭环，使每次算法迭代进步**可量化、可对比、可追溯**。

**三处核心改动**：
1. **多指标引导目标**：ALNS 接受准则从单一 λ 加权和扩展为 `obj/scale + w_bal·(1−balance) + w_flex·(1−flex)`，将负载均衡与可调整弹性纳入搜索引导
2. **相对改进率终止**：连续 N 轮改进 < δ 即停，替代固定时间限制
3. **迭代追溯快照**：`version → change → commit → metrics → delta` 完整链路，基准锁定四固定（实例/参考值/权重/seed）

**实验结果（medium，50 单 8 机，目标=最小化 ΣT）**：

| 版本 | ΣT | 负载均衡 | 弹性 | 综合评分 | 耗时 |
|---|---|---|---|---|---|
| v0 baseline（构造） | 8149 | 0.889 | 0.128 | 0.348 | 0.001s |
| v1 原 ALNS（纯目标） | 7348 | 0.897 | 0.113 | 0.349 | 20.0s |
| **v2 优化 ALNS**（多指标引导+智能终止） | 7631 | **0.923** | **0.124** | **0.355** | **3.1s** |

- 综合评分单调提升（0.348→0.349→0.355）
- 多指标引导提升负载均衡（0.897→0.923）
- 智能终止省时 84%（3.1s vs 20s）
- trade-off 诚实声明：ΣT 略升（7348→7631）换取负载均衡/弹性提升

详见 HTML 报告 `docs/算法迭代优化报告_medium.html`、方案 `docs/solution-quality-evaluation-design.md`。

---

## 目录结构

```
OR-Scheduling-Saas/
├── scripts/
│   ├── scheduler/          # 算法核心包
│   │   ├── model.py        # 数据模型 + 加载 + 体检 + 预检 + 评估
│   │   ├── cp_sat.py       # CP-SAT 精确求解（circuit 表达序列相关切换）
│   │   ├── heuristics.py   # 构造启发式（EDD/SPT/LPT）+ ALNS（多指标引导+智能终止）
│   │   ├── evaluation.py   # 解质量评价体系（7 指标 + 综合评分 + 迭代追溯快照）
│   │   ├── router.py       # 求解器路由（数据决定模型）
│   │   └── visualize.py    # 分层可视化（负载图/热力图/延误散点/甘特图）
│   ├── run_scheduler.py    # CLI 单层求解
│   ├── run_tests.py        # L1-L4 测试 + 约束验证
│   └── run_iteration.py    # 算法迭代优化实验 + HTML 报告
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

# 运行算法迭代优化实验（生成 HTML 报告）
python scripts/run_iteration.py
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
| 解质量评价体系方案 | `docs/solution-quality-evaluation-design.md` | 方案 V3（含 gap 检索 + 迭代追溯） |
| 算法迭代优化报告 | `docs/算法迭代优化报告_medium.html` | 迭代优化可视化 + 指标变化 |

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
