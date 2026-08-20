"""OR-Scheduling-SaaS API 入口。

路由挂载：/api/v1/auth, /api/v1/datasets, /api/v1/tasks, /api/v1/solutions
生产化（M4）：
- 全局限流中间件（每 IP 每分钟，排除探针/指标）
- HTTP 指标中间件（Prometheus 计数器 + 直方图）
- /metrics 指标端点 + /readyz 就绪探针（依赖检查）
启动时建 MongoDB 索引（幂等）。
"""
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .api.v1 import auth, datasets, solutions, tasks
from .core import metrics
from .core.config import settings
from .core.rate_limit import global_rate_limit_middleware
from .db.mongo import collections, ensure_indexes


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_indexes()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 限流中间件（先注册 = 内层）
app.middleware("http")(global_rate_limit_middleware)


# HTTP 指标中间件（后注册 = 外层，覆盖所有请求含被限流的 429）
@app.middleware("http")
async def http_metrics(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    route = request.scope.get("route")
    path = route.path if route is not None else request.url.path
    metrics.inc_counter(
        "http_requests_total",
        (("method", request.method), ("path", path), ("status", str(response.status_code))),
    )
    metrics.observe_histogram("http_request_duration_seconds", duration, (("method", request.method),))
    return response


app.include_router(auth.router, prefix="/api/v1")
app.include_router(datasets.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(solutions.router, prefix="/api/v1")


@app.get("/healthz", tags=["health"])
def healthz() -> dict:
    """存活探针（不依赖 MongoDB，liveness 用）。"""
    return {"status": "ok", "service": settings.app_name, "version": settings.version}


@app.get("/readyz", tags=["health"])
def readyz() -> dict:
    """就绪探针（readiness 用）：检查 MongoDB + Redis 可达。"""
    checks: dict[str, str] = {}
    try:
        collections()["tenants"].find_one()
        checks["mongo"] = "ok"
    except Exception:
        checks["mongo"] = "down"
    try:
        from .core.redis import get_redis

        get_redis().ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "down"
    ready = all(v == "ok" for v in checks.values())
    return {"status": "ready" if ready else "degraded", "checks": checks}


@app.get("/metrics", tags=["health"])
def metrics_endpoint() -> Response:
    """Prometheus 抓取端点（text/plain）。"""
    return Response(metrics.render(), media_type="text/plain; version=0.0.4")
