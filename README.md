# OR-Scheduling-SaaS

多机台智能排产 / 调度 SaaS（手术排程方向），求解内核基于 OR-Tools CP-SAT 精确求解 + 自研构造/ALNS 元启发 + 规模自动路由。

> **目录拼写说明**：开发工作区目录名为 `OR-Scheduing-Saas`（历史拼写错误，沿用）；交付 Git 仓库为 `OR-Scheduling-Saas`（正确拼写）。项目正式名称为 **OR-Scheduling-SaaS**。

---

## 三对话分工（总控视角）

| 对话 | 职责 | 状态 | 产出 |
|---|---|---|---|
| 1. 人格自举 + skill | OR-Expert 人格常驻 + 深度流程 | ✅ 完成 | `.hermes.md` + `personality-deploy/OR-Expert/` |
| 2. 算法开发 | 建模 + 求解 + 四层测试 | ✅ 完成 | `solver-core/`（原 `scripts/scheduler`，算法零改动包化） |
| 3. SaaS 总控（本对话） | 工程化 + API + 多租户 + 前端 | 🔄 进行中 | `backend/` `worker/` `frontend/` `deploy/` |

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
