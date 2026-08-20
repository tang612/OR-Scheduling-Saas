"""依赖注入：集合句柄 + 当前用户鉴权（JWT / API Token 双通道）。

- JWT：Authorization: Bearer <access_token>
- API Token：X-API-Key: <token>（长期凭证，脚本/CI 用）
"""
from typing import Optional

import jwt
from bson import ObjectId
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .security import decode_token, verify_api_token
from ..db.mongo import collections

_bearer = HTTPBearer(auto_error=False)


def _unauth() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "认证失败")


def get_collections() -> dict:
    return collections()


def _user_from_jwt(token: str) -> dict:
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise _unauth()
    if payload.get("type") != "access":
        raise _unauth()
    user = collections()["users"].find_one({"_id": ObjectId(payload["sub"])})
    if user is None:
        raise _unauth()
    return user


def _user_from_api_key(api_key: str) -> dict:
    prefix = api_key[:8]   # 前缀命中索引
    user = collections()["users"].find_one({"api_tokens.prefix": prefix})
    if user is None:
        raise _unauth()
    for t in user.get("api_tokens", []):
        if t["prefix"] == prefix and not t.get("revoked", False) and verify_api_token(api_key, t["hash"]):
            return user
    raise _unauth()


def get_current_user(
    authorization: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> dict:
    """解析当前用户（JWT 优先，其次 API Token）。返回 user 文档（含 _id/tenant_id/role）。"""
    if authorization is not None:
        return _user_from_jwt(authorization.credentials)
    if x_api_key:
        return _user_from_api_key(x_api_key)
    raise _unauth()
