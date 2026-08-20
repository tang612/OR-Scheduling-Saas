"""Redis 客户端、pub/sub 通道、取消标志。

- 队列：RQ 使用（进程级 worker，CPU 密集求解隔离）
- pub/sub：进度/事件四段式推送（Worker → Redis → API → SSE）
- 取消标志：跨进程可见（fork 后父子进程内存隔离，Redis 是唯一通道）
"""
import redis

from .config import settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Redis 客户端（懒连接，进程内单例，decode_responses=True 便于 JSON）。"""
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def task_channel(task_id: str) -> str:
    """进度/事件 pub/sub 通道名。"""
    return f"task:{task_id}"


def cancel_key(task_id: str) -> str:
    """取消标志 key（存在即取消）。"""
    return f"task:{task_id}:cancel"
