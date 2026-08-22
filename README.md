# OR-Scheduling-SaaS

多机台智能排产 / 调度 SaaS（手术排程方向），求解内核基于 OR-Tools CP-SAT 精确求解 + 自研构造/ALNS 元启发 + 规模自动路由。


---

## 对话分工（实际执行 · 与 commit 历史一一对应）

| 对话 | 职责 | 对应提交 | 产出 | 状态 |
|---|---|---|---|---|
| 1. 人格自举 + skill | OR-Expert 人格常驻 + 自举迭代（V2.1→V3.3，5 轮闭环） | 贯穿全程；V3.3 正式回写于交付整理轮（`8488840`） | `.hermes.md` + `personality-deploy/OR-Expert/`（SKILL.md v1.4.0 + references/v3-full.md V3.3）+ `docs/bootstrap-log.md`（5 轮自举日志）+ `docs/anti-hallucination-checklist.md` + `skills/`（开发/变更/调试三条流水线） | ✅ 完成 |
| 2. 算法开发 | 建模 + 求解 + 五层测试（L1~L5）+ 算法迭代 | `315563d` ~ `2b8f6f6` | `solver-core/`（model/cp_sat/heuristics/router/evaluation/visualize）+ `tests/unit/test_scheduler.py`（17/17 通过）+ `scripts/`（run_tests/run_scheduler/run_l5/run_iteration）+ `docs/algorithm_design.md` + `docs/test_reports/`（L1~L4）+ `docs/test-reports/`（L5 massive） | ✅ 完成 |
| 3. SaaS 工程化 | 工程化 + API + 多租户 + 异步求解 + 前端 + Dashboard 迭代 | `07a0045` ~ `d9d950b` | `backend/`（auth/datasets/tasks/solutions + 限流/TLS/监控）+ `worker/` + `frontend/`（Dashboard v2：状态机/SSE/甘特图/日志/分析面板）+ `deploy/`（compose + k8s）+ `docs/user-guide.md` + `docs/Dashboard_v2_过程报告.html` | ✅ 完成 |
| 4. 交付物整理与评审 | 交付物清单补齐（11 项）+ 文档评审索引 + V3.3 自举闭环回写 | `8488840` | `docs/PRD.md` + `docs/技术方案.md` + `docs/personality/运筹优化工程师-V3.3-最终版.md` + README §交付物清单 | ✅ 完成 |

---

## 交付物清单（评审索引 · 11 项）

| # | 交付物 | 位置 |
|---|---|---|
| ① | Personality 最终版文档（V3.3） | `docs/personality/运筹优化工程师-V3.3-最终版.md`（V3.0 基线：根目录同名 `.md/.docx`）+ `personality-deploy/OR-Expert/`（SKILL.md + references/v3-full.md） |
| ② | 自举迭代日志（5 轮） | `docs/bootstrap-log.md`（V2.1→V3.3 自举闭环） |
| ③ | 三条流水线 Skill 文件 | `skills/app-dev-flow`（开发流水线）`skills/change-request`（变更流水线）`skills/debug`（调试流水线） |
| ④ | PRD / 技术方案文档 | `docs/PRD.md` + `docs/技术方案.md`（算法需求规格：`docs/多机台智能排产_需求规格_阶段一.html`） |
| ⑤ | 反幻觉核对清单 | `docs/anti-hallucination-checklist.md` |
| ⑥ | Git commit 历史完整 | `git log`：Initial commit → M0/M1-M4 → L1~L5 测试 → Dashboard v1/v2，全程可追溯 |
| ⑦ | 算法核心代码（含单元测试） | `solver-core/`（model/cp_sat/heuristics/router/evaluation/visualize）+ `tests/unit/test_scheduler.py`（17/17 通过）+ `scripts/run_tests.py` |
| ⑧ | 四层测试报告（含性能数据） | `docs/test_reports/test_L1~L4.md` + `docs/test-reports/test_L5.md`（含耗时/gap/改进幅度） |
| ⑨ | FastAPI + MongoDB 后端 | `backend/`（auth/datasets/tasks/solutions + core 安全/限流/指标） |
| ⑩ | 前端界面（可视化排程结果） | `frontend/`（Dashboard/甘特图/日志/分析面板/SSE 实时进度） |
| ⑪ | 部署说明与运行脚本 | 本 README §快速开始 + `deploy/`（docker-compose / Dockerfile / nginx / k8s / .env.example）+ `scripts/`（run_tests / run_scheduler / run_l5 / run_iteration） |

**文档导航**：`docs/PRD.md`（产品需求）｜`docs/技术方案.md`（系统技术）｜`docs/algorithm_design.md`（算法方案）｜`docs/多机台智能排产_需求规格_阶段一.html`（需求规格+数学模型）｜`docs/solver-findings.md`（CP-SAT API 实证）｜`docs/user-guide.md`（用户指南）｜`docs/visualization_design.md` / `docs/solution-quality-evaluation-design.md`（可视化/质量评估设计）｜`docs/*_过程报告.html`（阶段过程报告）

---

## 架构（五层）

```
前端层(React) ──HTTPS──▶ API 网关(Nginx) ──REST/SSE──▶ 业务逻辑层(FastAPI)
                                                          │ 鉴权/租户路由/校验
                                          Redis(队列+进度总线)◀──┘
                                                          │
                                                          ▼
                                                    业务逻辑层(Worker/RQ)
                                                          │
                                                          ▼
                                          求解器层(CP-SAT / ALNS / 规模路由)
                                                          │
                                                          ▼
                                          数据层(MongoDB: 任务/方案/日志)
```

---

## 目录结构

```
OR-Scheduing-Saas/
├── solver-core/            # 求解核心包（pip install -e 可装）
│   ├── pyproject.toml
│   └── scheduler/          # model/cp_sat/heuristics/router/evaluation/visualize
├── backend/                # FastAPI 服务
│   ├── requirements.txt
│   └── app/
│       ├── main.py         # 入口 + /healthz
│       └── core/           # config.py（pydantic-settings）
├── worker/                 # 异步任务（M2 填充：RQ job + engines 注册表）
├── frontend/               # React SPA（M3 填充）
├── deploy/
│   ├── docker-compose.yml  # mongo/redis/api/nginx
│   ├── Dockerfile.api
│   └── nginx.conf
├── scripts/                # 原 CLI 调试入口（指向 solver-core）
├── docs/                   # 算法设计/测试报告/求解器发现
└── personality-deploy/     # OR-Expert 人格源稿
```

---

## 里程碑

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | 骨架 + solver-core 包化 + Docker 化 | ✅ |
| M1 | 认证 + 数据模型 + 任务提交（同步版） | ✅ |
| M2 | 异步任务 + Redis/RQ + SSE 实时进度 | ✅ |
| M3 | 多引擎封装 + 甘特图 + 约束配置表单 | ✅ |
| M4 | 生产化（限流/TLS/监控/K8s） | ✅ |

---

## 求解器规模路由（`router.solve` 内建）

| 订单数 n | 策略 |
|---|---|
| n ≤ 20 | CP-SAT 精确 |
| n ≤ 80 | 构造 + ALNS 300s |
| n ≤ 300 | 构造 + ALNS 900s |
| else | 构造 + ALNS 900s |

---

## 开发环境约定

- **本机**：miniconda Python 3.14.6 + ortools 9.15.6755（官方 wheel 支持 cp314）
- **solver-core** 以 editable 安装：`pip install -e solver-core`
- **Docker 是唯一运行时真相**：`python:3.14-slim`（与决策点 1 一致）

## 快速开始

### 本机开发

```bash
pip install -e solver-core
pip install -r backend/requirements.txt
cd backend && uvicorn app.main:app --reload
# → http://127.0.0.1:8000/healthz
```

### Docker（需 Docker Desktop）

```bash
cd deploy
cp .env.example .env   # 填 JWT_SECRET
docker compose up -d --build
curl http://localhost:8080/healthz
```

---

## 已确立的架构决策（第一性原理审查后）

1. **Python 3.14-slim** 基础镜像（ortools 官方 wheel 验证支持 cp314）
2. **Gurobi 引擎默认不启用**（需商业/学术 license，仅留接口）
3. **取消/进度通道 = Redis 标志位 + pub/sub**（fork 进程跨进程可见，`threading.Event` 跨进程失效已规避）
4. **一致性 = 幂等键 + 状态机 + 补偿**（单实例 MongoDB 无跨集合事务，替代方案已定）
5. **SSE 四段式**（Worker → Redis pub/sub → API → 浏览器），API 无状态可水平扩展
