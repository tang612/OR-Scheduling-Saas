# OR-Scheduling-SaaS 用户操作指南

> 面向终端用户（排产员 / 手术室调度员）：不要求懂算法，只需「准备数据 → 上传 → 提交 → 查看甘特图」四步。
> 本指南所有接口、字段、行为均已在本机实测验证。

---

## 目录

1. [系统简介](#一系统简介)
2. [快速开始（启动与访问）](#二快速开始启动与访问)
3. [首次使用：注册与登录](#三首次使用注册与登录)
4. [准备排产数据](#四准备排产数据)
5. [上传数据集](#五上传数据集)
6. [提交求解任务](#六提交求解任务)
7. [查看进度与结果](#七查看进度与结果)
8. [求解器与参数怎么选](#八求解器与参数怎么选)
9. [常见问题](#九常见问题)
10. [进阶：REST API 速查](#十进阶rest-api-速查)

---

## 一、系统简介

多机台智能排产系统：把 **机器、订单、工艺配方、配方切换成本** 四类数据交进去，系统自动算出「哪台机器、按什么顺序、几点做哪个订单」的最优排程，并输出甘特图。

- 小规模（订单 ≤ 20）：**CP-SAT 精确求解**，秒级拿到最优解
- 大规模：**构造 + ALNS 元启发式**，限时求高质量可行解
- 求解器由系统按规模自动选择，用户无需关心内部算法

**实测能力示例**（toy 数据 5 订单 × 3 机器）：

| 指标 | 值 |
|---|---|
| 求解器 | CP-SAT |
| 状态 | OPTIMAL（已证明最优） |
| makespan（总完工时间） | 90 |
| ΣT（拖期总和） | 82 |
| 求解耗时 | 0.01 s |

---

## 二、快速开始（启动与访问）

### 启动系统（管理员执行一次）

```bash
cd OR-Scheduing-Saas/deploy
cp .env.example .env        # 首次执行；模板默认 dev 模式，可直接启动
docker compose up -d --build
```

> 首次构建约几分钟（拉取镜像 + 安装依赖），之后日常只需 `docker compose up -d`（秒级）。
> **代码没改时不要重复 `--build`**，会拖慢且无必要。

### 访问

浏览器打开 **http://localhost:8080**，看到登录页即成功。

> 本机同时提供 HTTPS 入口 `https://localhost:8443`（自签证书，浏览器需点「高级 → 继续前往」）。

### 验证启动成功

```bash
curl http://localhost:8080/healthz
# 期望返回：{"status":"ok","service":"OR-Scheduling-SaaS","version":"0.1.0"}
```

---

## 三、首次使用：注册与登录

1. 登录页点「**去注册**」
2. 填 **邮箱**（合法格式）+ **密码（≥ 8 位）**
3. 注册成功后自动回到登录页，用同一账号登录

> **多租户隔离**：每个账号一个独立租户，你上传的数据集、任务、方案只有自己可见，同系统其他租户互不可见。

---

## 四、准备排产数据

数据集是**一个 JSON 对象**，含 4 个必需字段：`machines` / `orders` / `recipes` / `switch_matrix`。

### 字段说明

| 字段 | 含义 | 说明 |
|---|---|---|
| `machines[]` | 机台清单 | `id`、`name`(可选)、`allowed_recipes`(该机台能加工的配方)、`cleanup_time`(机台清理耗时) |
| `recipes[]` | 工艺配方 | `id`、`processing_time`(单件加工时间) |
| `orders[]` | 订单 | `id`、`recipe_id`(加工配方)、`quantity`(数量)、`due_time`(交期)、`priority`(优先级，越大越紧急，可省) |
| `switch_matrix` | 配方间切换成本 | `recipes`(配方 ID 顺序) + `matrix`(N×N 矩阵)；`matrix[i][j]` = 从配方 i 切到配方 j 的耗时；**`null` 表示不可切换（硬约束）** |

### 完整示例（可直接粘贴）

```json
{
  "machines": [
    { "id": "m1", "name": "CNC-01",  "allowed_recipes": ["r1", "r2", "r3"], "cleanup_time": 1 },
    { "id": "m2", "name": "LATHE-01","allowed_recipes": ["r1", "r2", "r3"], "cleanup_time": 3 },
    { "id": "m3", "name": "MILL-01", "allowed_recipes": ["r1", "r2", "r3"], "cleanup_time": 3 }
  ],
  "recipes": [
    { "id": "r1", "processing_time": 5 },
    { "id": "r2", "processing_time": 9 },
    { "id": "r3", "processing_time": 7 }
  ],
  "orders": [
    { "id": "order_0001", "recipe_id": "r1", "quantity": 7,  "due_time": 18, "priority": 1 },
    { "id": "order_0002", "recipe_id": "r2", "quantity": 10, "due_time": 25, "priority": 2 },
    { "id": "order_0003", "recipe_id": "r3", "quantity": 1,  "due_time": 35, "priority": 3 },
    { "id": "order_0004", "recipe_id": "r2", "quantity": 2,  "due_time": 84, "priority": 5 },
    { "id": "order_0005", "recipe_id": "r1", "quantity": 10, "due_time": 93, "priority": 1 }
  ],
  "switch_matrix": {
    "recipes": ["r1", "r2", "r3"],
    "matrix": [
      [2, 8, 6],
      [7, 1, 7],
      [7, 6, 2]
    ]
  }
}
```

### 数据校验（上传前系统自动体检）

以下情况会在上传时被拦截并给出具体错误码，不会入库：

- 缺少 `machines/orders/recipes/switch_matrix` 任一项
- 订单引用了不存在的 `recipe_id`
- 机器 `allowed_recipes` 引用了不存在的配方
- `switch_matrix.matrix` 尺寸与 `recipes` 数量不一致

---

## 五、上传数据集

1. 进入「**提交任务**」页 → 上半区「上传数据集」
2. 填**数据集名称**（如「周二排程」）
3. 把上一步的 JSON 粘贴进文本框
4. 点「**上传数据集**」

成功后提示「数据集已上传（5 单 × 3 机）」，并出现在下方任务表单的「数据集」下拉框中。同一数据集可反复用于多个求解任务。

---

## 六、提交求解任务

| 配置项 | 说明 | 推荐 |
|---|---|---|
| **任务名称** | 自定义，便于列表区分 | 如「周二排程-方案A」 |
| **数据集** | 下拉选择 | — |
| **λ 权重** | 三个目标权重，逗号分隔，顺序 `(makespan, tardiness, completion)` | 见下节 |
| **求解器** | `自动` / `CP-SAT 精确` / `构造+ALNS` / `全部对比` | 一般选**自动** |
| **时间预算(秒)** | 可选，限制求解时长 | 见下节 |

### λ 权重怎么设（目标函数）

系统目标 = `λ₁·makespan + λ₂·ΣT + λ₃·ΣC`

| 权重 | 含义 | 适用场景 |
|---|---|---|
| `0,1,0`（默认） | 只优化 ΣT（拖期总和），尽量少延误 | 赶交期、客户准时优先 |
| `1,0,0` | 只优化 makespan（总完工时间），最快做完 | 产能优先 |
| `1,1,0` | 均衡「快」与「少延误」 | 日常排产 |

---

## 七、查看进度与结果

提交后自动跳转任务详情页：

1. **实时进度**（SSE 自动推送，无需刷新）：状态徽标（排队中 → 求解中 → 完成/失败）+ 进度条 + 阶段文字（构建模型 / CP-SAT 求解 / ALNS 迭代…）
2. **完成后出现方案对比表**：

| 引擎 | 状态 | makespan | ΣT | ΣC | gap | 耗时 |
|---|---|---|---|---|---|---|
| CP-SAT | OPTIMAL | 90 | 82 | 254 | 0.000 | 0.01s |
| ALNS | FEASIBLE | ... | ... | ... | ... | ...s |

3. **甘特图**：点方案行的「查看」按钮，横轴时间、纵轴机台，色块 = 订单（拖期订单高亮），直观看到每台机器每个时段的排程与切换段。

**指标含义**：

- **makespan** = 总完工时间（最后一个订单完成时刻），越小越快
- **ΣT** = 拖期总和（各订单超过交期的时长之和），越小越准时
- **ΣC** = 完工时间总和
- **gap** = 与最优解的相对差距（0 = 已证明最优；数值越小越好）

---

## 八、求解器与参数怎么选

| 场景 | 建议 | 说明 |
|---|---|---|
| 订单 ≤ 20，要最优解 | **自动** | 自动路由到 CP-SAT，秒级出 OPTIMAL |
| 订单 20~80 | **自动** | 路由到 ALNS（300s 预算） |
| 订单 > 80 | **自动** | 路由到 ALNS（900s 预算） |
| 要双引擎对比、可等待 | **全部对比** | 见下方提醒 |
| 求快、先要粗方案 | 任意引擎 + 填**时间预算** | 如填 `30`，30 秒后返回当前最优 |

### ⚠️ 「全部对比」模式耗时提醒（实测）

「全部对比」= 依次跑 **CP-SAT + ALNS** 两个引擎。CP-SAT 秒级完成，但 **ALNS 默认预算 300 秒**（未填时间预算时），因此任务会在约 5 分钟后才结束——这不是卡死，是 ALNS 在按预算迭代优化。

**建议**：选「全部对比」时务必填写**时间预算**（如 `30`~`60` 秒），或小数据直接用「自动」（秒级 CP-SAT）。

---

## 九、常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 上传报 `[E-xxx]` 错误 | 数据体检拦截：配方引用不存在、矩阵尺寸不对等，按提示修正 JSON |
| 提交任务报「不可行」 | 产能不足或切换硬约束无解，调整交期或放宽机器限制 |
| 任务长时间「求解中」 | 「全部对比」模式下 ALNS 默认 300s，属正常；或填时间预算缩短 |
| `null` 切换项 | 表示该配方对不可切换，是**硬约束**，不是漏填 |
| 页面一直「排队中」 | worker 容器未运行或繁忙，`docker compose ps` 检查 `deploy-worker-1` |
| 甘特图空白 | 该方案求解失败（如数据不可行），看方案行 status 列 |
| 访问 http 打不开 / 502 | 见下方「部署排障」 |

### 部署排障（管理员）

| 现象 | 处理 |
|---|---|
| api 容器 `unhealthy`（JWT_SECRET 校验失败） | `.env` 的 `JWT_SECRET` 需 ≥32 字节：`python3 -c "import secrets; print(secrets.token_hex(32))"` 生成后填入；或 `ENVIRONMENT=dev`（弱密钥允许） |
| api 重建后 nginx 报 502 | 重启 nginx：`docker compose restart nginx`（已通过 DNS resolver 根治，新部署不会出现） |
| 反复 `cp .env.example .env` 覆盖密钥 | 模板默认 `ENVIRONMENT=dev` 已可开箱启动；生产部署再改 `prod` + 强密钥 |

---

## 十、进阶：REST API 速查

所有界面功能均有 REST 接口（Base：`http://localhost:8080/api/v1`），适合脚本/系统集成。鉴权：登录返回的 JWT 放 `Authorization: Bearer <token>`。

```bash
# 1. 注册
curl -X POST http://localhost:8080/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"你的密码≥8位","tenant_name":"我的租户"}'

# 2. 登录（拿 token）
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"你的密码"}'

# 3. 上传数据集（body 即第四节 JSON + name）
curl -X POST http://localhost:8080/api/v1/datasets \
  -H "Authorization: Bearer <token>" -H 'Content-Type: application/json' \
  -d '{"name":"周二排程", ...四字段...}'

# 4. 提交任务
curl -X POST http://localhost:8080/api/v1/tasks \
  -H "Authorization: Bearer <token>" -H 'Content-Type: application/json' \
  -d '{"name":"周二排程求解","dataset_id":"<id>","config":{"lambda":[0,1,0],"solver":"auto"}}'

# 5. 订阅实时进度（SSE）
curl -N http://localhost:8080/api/v1/tasks/<task_id>/events \
  -H "Authorization: Bearer <token>"

# 6. 查询方案 / 甘特图
curl http://localhost:8080/api/v1/tasks/<task_id>/solutions   -H "Authorization: Bearer <token>"
curl http://localhost:8080/api/v1/solutions/<solution_id>     -H "Authorization: Bearer <token>"

# 7. 取消任务
curl -X DELETE http://localhost:8080/api/v1/tasks/<task_id> -H "Authorization: Bearer <token>"
```

---

**一句话总结**：注册登录 → 粘贴 JSON 数据 → 提交任务（小数据选「自动」）→ 等进度 → 看甘特图。系统内部自动完成「数据体检 → 模型构建 → 求解器选型 → 异步求解 → 方案对比」。
