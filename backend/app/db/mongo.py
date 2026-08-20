"""MongoDB 连接、集合定义与索引（幂等创建）。

集合：tenants / users / datasets / tasks / solutions
多租户隔离铁律：所有 Repository 查询强制携带 tenant_id 前缀。
"""
from pymongo import ASCENDING, DESCENDING, MongoClient

from ..core.config import settings

_client: MongoClient | None = None


def get_db():
    """返回数据库实例（懒连接，进程内单例）。数据库名取自 MONGO_URI。"""
    global _client
    if _client is None:
        _client = MongoClient(settings.mongo_uri, tz_aware=True)
    return _client.get_default_database()


def collections() -> dict:
    db = get_db()
    return {
        "tenants": db["tenants"],
        "users": db["users"],
        "datasets": db["datasets"],
        "tasks": db["tasks"],
        "solutions": db["solutions"],
    }


def ensure_indexes() -> None:
    """创建索引（幂等），FastAPI lifespan 启动时调用。"""
    db = get_db()
    # users：email 全局唯一（一个账号一个租户）
    db["users"].create_index([("email", ASCENDING)], unique=True)
    db["users"].create_index([("tenant_id", ASCENDING)])
    # datasets：租户内按创建时间倒序
    db["datasets"].create_index(
        [("tenant_id", ASCENDING), ("created_at", DESCENDING)]
    )
    # tasks：列表页按租户+状态+时间过滤；详情按租户+id
    db["tasks"].create_index(
        [("tenant_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)]
    )
    db["tasks"].create_index([("tenant_id", ASCENDING), ("_id", ASCENDING)])
    # solutions：多方案对比（同任务多引擎）；租户内倒序
    db["solutions"].create_index(
        [("task_id", ASCENDING), ("engine", ASCENDING)], unique=True
    )
    db["solutions"].create_index(
        [("tenant_id", ASCENDING), ("created_at", DESCENDING)]
    )
