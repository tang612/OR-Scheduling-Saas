"""OR-Scheduling-SaaS API 入口。

M0：仅存活探针；M1 挂载 auth/datasets/tasks 路由。
"""
from fastapi import FastAPI

from .core.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)


@app.get("/healthz", tags=["health"])
def healthz() -> dict:
    """存活探针：docker-compose healthcheck 与 K8s liveness 共用。"""
    return {"status": "ok", "service": settings.app_name, "version": settings.version}
