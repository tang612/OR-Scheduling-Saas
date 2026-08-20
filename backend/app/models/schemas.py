"""Pydantic v2 请求/响应模型。

ID 一律以 str 表达（MongoDB ObjectId 在边界层转换）。
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=72)
    tenant_name: str = Field(default="默认租户", max_length=100)


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ApiTokenOut(BaseModel):
    prefix: str
    name: str
    created_at: datetime
    revoked: bool


class ApiTokenCreated(ApiTokenOut):
    """签发成功时返回一次明文 token。"""
    token: str


# ---------------------------------------------------------------------------
# Dataset（五 JSON 的规范化输入）
# ---------------------------------------------------------------------------

class MachineIn(BaseModel):
    id: str
    name: Optional[str] = None
    allowed_recipes: list[str]
    cleanup_time: int = Field(ge=0)


class RecipeIn(BaseModel):
    id: str
    processing_time: int = Field(gt=0)


class OrderIn(BaseModel):
    id: str
    recipe_id: str
    quantity: int = Field(gt=0)
    due_time: int = Field(ge=0)
    priority: int = 0


class SwitchMatrixIn(BaseModel):
    recipes: list[str]
    matrix: list[list[Optional[int]]]  # null = 不可切换


class DatasetIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    machines: list[MachineIn]
    orders: list[OrderIn]
    recipes: list[RecipeIn]
    switch_matrix: SwitchMatrixIn


class DatasetOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    num_orders: int
    num_machines: int
    num_recipes: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Task / Solution
# ---------------------------------------------------------------------------

class TaskConfig(BaseModel):
    # JSON 字段名用 "lambda"（λ 权重），Python 侧字段名 weights
    weights: tuple[float, float, float] = Field(
        default=(0.0, 1.0, 0.0), alias="lambda"
    )
    solver: str = "auto"          # auto | cpsat | alns
    time_budget: Optional[float] = None
    seed: int = 42


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    dataset_id: str
    config: TaskConfig = TaskConfig()


class TaskOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    dataset_id: str
    status: str
    progress: float
    stage: str
    solver: Optional[str] = None
    objective: Optional[dict] = None
    error: Optional[dict] = None
    created_at: datetime
    finished_at: Optional[datetime] = None


class SolutionOut(BaseModel):
    id: str
    task_id: str
    engine: str
    status: str
    objective: dict
    gap: Optional[float] = None
    solve_time_s: float
    created_at: datetime
