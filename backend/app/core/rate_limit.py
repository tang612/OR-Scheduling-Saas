"""Redis 限流：固定窗口（INCR + 首次 EXPIRE）。

- 全局 API 限流中间件（每 IP 每分钟 N 次，排除探针/指标/文档路径）
- 登录/注册限流依赖（防暴力破解，更严格）
客户端 IP 优先取 X-Forwarded-For（nginx 反代注入），否则取直连地址。
"""
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from .config import settings
from .redis import get_redis

_EXEMPT_PREFIXES = ("/healthz", "/readyz", "/metrics", "/api/docs", "/api/openapi.json")


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(key: str, limit: int, window: int) -> None:
    """固定窗口限流：INCR 并首次 EXPIRE；超限抛 429。"""
    r = get_redis()
    try:
        count = r.incr(key)
        if count == 1:
            r.expire(key, window)
        if count > limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "请求过于频繁，请稍后再试")
    except HTTPException:
        raise
    except Exception:
        # Redis 不可用时降级放行（限流是保护，不应拖垮主链路）
        return


def auth_rate_limit(request: Request) -> None:
    """登录/注册防暴力破解限流（每 IP 每分钟 N 次）。"""
    check_rate_limit(f"ratelimit:auth:{client_ip(request)}", settings.auth_rate_limit_per_min, 60)


async def global_rate_limit_middleware(request: Request, call_next):
    """全局 API 限流中间件（每 IP 每分钟 N 次）。"""
    if request.url.path.startswith(_EXEMPT_PREFIXES):
        return await call_next(request)
    key = f"ratelimit:global:{client_ip(request)}"
    try:
        check_rate_limit(key, settings.rate_limit_per_min, 60)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    return await call_next(request)
