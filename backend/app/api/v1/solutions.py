"""方案路由：多方案列表 + 单方案详情（含甘特图块数据）。

甘特图数据从 solution.schedule（assignment/sequences/start/end）+ dataset.data 反推：
machines（资源）/ jobs（订单块）/ setup（切换块）。
"""
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from ...core.deps import get_collections, get_current_user
from ...models.schemas import SolutionOut

router = APIRouter(tags=["solutions"])


def _build_gantt(solution: dict, dataset: dict) -> dict:
    """从 schedule + dataset 反推甘特图块数据。"""
    schedule = solution.get("schedule") or {}
    machines_raw = dataset["data"]["machines"]
    orders_raw = dataset["data"]["orders"]

    machines = [{"id": m["id"], "name": m.get("name", m["id"])} for m in machines_raw]

    assignment = schedule.get("assignment", [])
    sequences = schedule.get("sequences", [])
    start = schedule.get("start", [])
    end = schedule.get("end", [])

    jobs = []
    for j, o in enumerate(orders_raw):
        m_idx = assignment[j] if j < len(assignment) else -1
        if m_idx < 0:
            continue
        jobs.append({
            "id": o["id"],
            "machine": machines_raw[m_idx]["id"],
            "start": start[j] if j < len(start) else 0,
            "end": end[j] if j < len(end) else 0,
            "recipe": o["recipe_id"],
            "tardy": (end[j] if j < len(end) else 0) > o["due_time"],
            "due": o["due_time"],
        })

    # setup 块：每台机器序列里相邻订单之间的切换（含清理）
    setup_blocks = []
    for m_idx, seq in enumerate(sequences):
        for k in range(len(seq) - 1):
            j1, j2 = seq[k], seq[k + 1]
            setup_blocks.append({
                "id": f"setup_{m_idx}_{k}",
                "machine": machines_raw[m_idx]["id"],
                "start": end[j1] if j1 < len(end) else 0,
                "end": start[j2] if j2 < len(start) else 0,
                "type": "switch",
            })

    return {
        "machines": machines,
        "jobs": jobs,
        "setup": setup_blocks,
        "meta": {
            "makespan": solution["objective"].get("makespan"),
            "tardiness": solution["objective"].get("tardiness"),
            "completion": solution["objective"].get("completion"),
            "solver": solution["engine"],
            "status": solution["status"],
            "gap": solution.get("gap"),
            "solve_time_s": solution.get("solve_time_s"),
        },
    }


def _to_out(s: dict) -> SolutionOut:
    return SolutionOut(
        id=str(s["_id"]), task_id=str(s["task_id"]), engine=s["engine"],
        status=s["status"], objective=s["objective"], gap=s.get("gap"),
        solve_time_s=s.get("solve_time_s", 0.0), created_at=s["created_at"],
    )


@router.get("/tasks/{task_id}/solutions", response_model=list[SolutionOut])
def list_solutions(
    task_id: str,
    user=Depends(get_current_user),
    cols=Depends(get_collections),
) -> list[SolutionOut]:
    task = cols["tasks"].find_one(
        {"_id": ObjectId(task_id), "tenant_id": user["tenant_id"]}
    )
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    docs = cols["solutions"].find({"task_id": ObjectId(task_id)}).sort("created_at", 1)
    return [_to_out(s) for s in docs]


@router.get("/solutions/{solution_id}")
def get_solution(
    solution_id: str,
    user=Depends(get_current_user),
    cols=Depends(get_collections),
) -> dict:
    s = cols["solutions"].find_one(
        {"_id": ObjectId(solution_id), "tenant_id": user["tenant_id"]}
    )
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "方案不存在")
    task = cols["tasks"].find_one({"_id": s["task_id"]})
    dataset = cols["datasets"].find_one({"_id": task["dataset_id"]})
    out = _to_out(s).model_dump()
    out["gantt"] = _build_gantt(s, dataset)
    return out
