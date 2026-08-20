"""数据集路由：上传（Pydantic 校验 + solver-core 体检）、列表、详情。"""
import hashlib
import json
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from scheduler.model import DataError

from ...core.deps import get_collections, get_current_user
from ...models.schemas import DatasetIn, DatasetOut
from ...services.solver_service import dataset_to_data_model

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _checksum(data: dict) -> str:
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _to_out(d: dict) -> DatasetOut:
    return DatasetOut(
        id=str(d["_id"]), tenant_id=str(d["tenant_id"]), name=d["name"],
        num_orders=d["num_orders"], num_machines=d["num_machines"],
        num_recipes=d["num_recipes"], created_at=d["created_at"],
    )


@router.post("", status_code=201, response_model=DatasetOut)
def create_dataset(
    body: DatasetIn,
    user=Depends(get_current_user),
    cols=Depends(get_collections),
) -> DatasetOut:
    data = {
        "machines": [m.model_dump(exclude_none=True) for m in body.machines],
        "orders": [o.model_dump() for o in body.orders],
        "recipes": [r.model_dump() for r in body.recipes],
        "switch_matrix": body.switch_matrix.model_dump(),
    }
    # solver-core 体检（配方引用、switch_matrix 一致性、空输入、字段缺失）
    try:
        dm = dataset_to_data_model(data)
    except DataError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"[{e.code}] {e.msg}")

    doc = {
        "tenant_id": user["tenant_id"],
        "name": body.name,
        "version": 1,
        "data": data,
        "checksum": _checksum(data),
        "num_orders": dm.n,
        "num_machines": dm.m,
        "num_recipes": len(dm.recipes),
        "created_at": datetime.now(timezone.utc),
    }
    ds_id = cols["datasets"].insert_one(doc).inserted_id
    doc["_id"] = ds_id
    return _to_out(doc)


@router.get("", response_model=list[DatasetOut])
def list_datasets(
    user=Depends(get_current_user),
    cols=Depends(get_collections),
) -> list[DatasetOut]:
    docs = cols["datasets"].find({"tenant_id": user["tenant_id"]}).sort("created_at", -1)
    return [_to_out(d) for d in docs]


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(
    dataset_id: str,
    user=Depends(get_current_user),
    cols=Depends(get_collections),
) -> DatasetOut:
    d = cols["datasets"].find_one(
        {"_id": ObjectId(dataset_id), "tenant_id": user["tenant_id"]}
    )
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "数据集不存在")
    return _to_out(d)
