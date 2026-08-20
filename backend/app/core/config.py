"""集中配置：环境变量注入（docker-compose / K8s）。

M0 仅承载存活探针所需的字段；数据层/鉴权字段在 M1 启用时补充。
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "OR-Scheduling-SaaS"
    version: str = "0.1.0"

    # 数据层（M1 起用）
    mongo_uri: str = "mongodb://localhost:27017/or_scheduling"
    redis_url: str = "redis://localhost:6379/0"

    # 鉴权（M1 起用）
    jwt_secret: str = "dev-secret-change-me"
    jwt_access_ttl_min: int = 15
    jwt_refresh_ttl_days: int = 7

    # 跨域（前端 dev server）
    cors_origins: str = "http://localhost:5173"


settings = Settings()
