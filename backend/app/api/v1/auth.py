"""认证路由：注册 / 登录 / 刷新 / API Token 签发与列表。"""
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel

from ...core.deps import get_collections, get_current_user
from ...core.rate_limit import auth_rate_limit
from ...core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_api_token,
    hash_password,
    verify_password,
)
from ...models.schemas import (
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenOut,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/register", status_code=201)
def register(body: RegisterRequest, cols=Depends(get_collections), _=Depends(auth_rate_limit)) -> dict:
    users, tenants = cols["users"], cols["tenants"]
    if users.find_one({"email": body.email}):
        raise HTTPException(status.HTTP_409_CONFLICT, "邮箱已注册")

    now = datetime.now(timezone.utc)
    tenant_id = tenants.insert_one({
        "name": body.tenant_name,
        "plan": "free",
        "quota": {"max_concurrent_jobs": 3, "max_dataset_mb": 50},
        "created_at": now,
    }).inserted_id
    user_id = users.insert_one({
        "tenant_id": tenant_id,
        "email": body.email,
        "hashed_password": hash_password(body.password),
        "role": "admin",
        "api_tokens": [],
        "created_at": now,
    }).inserted_id
    return {"id": str(user_id), "email": body.email, "tenant_id": str(tenant_id)}


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, cols=Depends(get_collections), _=Depends(auth_rate_limit)) -> TokenResponse:
    user = cols["users"].find_one({"email": body.email})
    if user is None or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "邮箱或密码错误")
    uid, tid, role = str(user["_id"]), str(user["tenant_id"]), user["role"]
    return TokenResponse(
        access_token=create_access_token(uid, tid, role),
        refresh_token=create_refresh_token(uid, tid, role),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, cols=Depends(get_collections)) -> TokenResponse:
    try:
        payload = decode_token(body.refresh_token)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "refresh token 无效或已过期")
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "非 refresh token")
    uid, tid, role = payload["sub"], payload["tenant_id"], payload["role"]
    return TokenResponse(
        access_token=create_access_token(uid, tid, role),
        refresh_token=create_refresh_token(uid, tid, role),
    )


@router.post("/api-tokens", response_model=ApiTokenCreated, status_code=201)
def create_api_token(
    body: ApiTokenCreate,
    user=Depends(get_current_user),
    cols=Depends(get_collections),
) -> ApiTokenCreated:
    raw, prefix, hashed = generate_api_token()
    token_doc = {
        "prefix": prefix,
        "hash": hashed,
        "name": body.name,
        "created_at": datetime.now(timezone.utc),
        "revoked": False,
    }
    cols["users"].update_one({"_id": user["_id"]}, {"$push": {"api_tokens": token_doc}})
    return ApiTokenCreated(
        token=raw, prefix=prefix, name=body.name,
        created_at=token_doc["created_at"], revoked=False,
    )


@router.get("/api-tokens", response_model=list[ApiTokenOut])
def list_api_tokens(user=Depends(get_current_user)) -> list[ApiTokenOut]:
    return [
        ApiTokenOut(
            prefix=t["prefix"], name=t["name"],
            created_at=t["created_at"], revoked=t.get("revoked", False),
        )
        for t in user.get("api_tokens", [])
    ]
