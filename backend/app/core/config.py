"""集中配置：环境变量注入（docker-compose / K8s）。

environment 区分 dev/prod：prod 下 JWT_SECRET 强制 ≥32 字节，否则拒绝启动。
"""
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "OR-Scheduling-SaaS"
    version: str = "0.1.0"
    environment: str = "dev"  # dev / prod

    # 数据层
    mongo_uri: str = "mongodb://localhost:27017/or_scheduling"
    redis_url: str = "redis://localhost:6379/0"

    # 鉴权
    jwt_secret: str = "dev-secret-change-me"
    jwt_access_ttl_min: int = 15
    jwt_refresh_ttl_days: int = 7

    # 限流（M4）：每 IP 每分钟
    rate_limit_per_min: int = 120          # 全局 API 限流
    auth_rate_limit_per_min: int = 5       # 登录/注册防暴力破解

    # 跨域
    cors_origins: str = "http://localhost:5173"

    @model_validator(mode="after")
    def _check_prod_secret(self) -> "Settings":
        if self.environment == "prod" and len(self.jwt_secret) < 32:
            raise ValueError(
                f"生产环境 JWT_SECRET 必须 ≥32 字节（当前 {len(self.jwt_secret)} 字节）。"
                '生成：python3 -c "import secrets; print(secrets.token_hex(32))"'
            )
        return self


settings = Settings()
