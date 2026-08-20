"""安全工具：密码哈希、JWT 编解码、API Token 生成/校验。

- 密码与 API Token 均用 bcrypt 哈希存储，明文不落库。
- JWT 用 PyJWT（HS256），access 短效 / refresh 长效。
"""
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings

# bcrypt 密码上限 72 字节
_BCRYPT_MAX_BYTES = 72


# ---------------------------------------------------------------------------
# 密码哈希
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """bcrypt 哈希密码。"""
    pw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        pw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
        return bcrypt.checkpw(pw, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def _encode_token(sub: str, tenant_id: str, role: str, token_type: str, exp: datetime) -> str:
    payload = {
        "sub": sub,            # user_id (str)
        "tenant_id": tenant_id,
        "role": role,
        "type": token_type,
        "iat": datetime.now(timezone.utc),
        "exp": exp,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_access_token(sub: str, tenant_id: str, role: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_ttl_min)
    return _encode_token(sub, tenant_id, role, "access", exp)


def create_refresh_token(sub: str, tenant_id: str, role: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_ttl_days)
    return _encode_token(sub, tenant_id, role, "refresh", exp)


def decode_token(token: str) -> dict:
    """解码并校验 JWT；失败抛 jwt.PyJWTError（含过期/签名错误）。"""
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


# ---------------------------------------------------------------------------
# API Token（长期凭证，供脚本/CI 调用）
# ---------------------------------------------------------------------------

def generate_api_token() -> tuple[str, str, str]:
    """生成 API Token，返回 (明文, 前缀, 哈希)。明文仅本次返回，不可再取。"""
    raw = secrets.token_urlsafe(32)
    prefix = raw[:8]                       # 前缀：索引命中用
    hashed = bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    return raw, prefix, hashed


def verify_api_token(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
