#!/usr/bin/env python3
"""CLI：求解指定数据目录，输出 JSON 结果 + 分层可视化。

用法: python3 scripts/run_scheduler.py <数据目录> [--lambda 0,1,0] [--time 秒] [--out 输出目录]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from scheduler.model import load_data, feasibility_check
from scheduler.router import solve
from scheduler import visualize


def main():
    ap = argparse.ArgumentParser(description="多机台智能排产求解器")
    ap.add_argument("data_dir", help="数据目录（含 5 个 JSON）")
    ap.add_argument("--lambda", dest="lam", default="0,1,0",
                    help="目标权重 λ1,λ2,λ3（makespan,tardiness,total_completion）")
    ap.add_argument("--time", type=float, default=None, help="时间预算（秒）")
    ap.add_argument("--out", default="docs/results", help="输出目录")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-viz", action="store_true", help="跳过可视化")
    args = ap.parse_args()

    lam = tuple(float(x) for x in args.lam.split(","))
    if len(lam) != 3 or not any(lam):
        sys.exit("λ 必须是三个非负值，至少一个非零，如 0,1,0")

    print(f"=== 加载数据: {args.data_dir} ===")
    data = load_data(args.data_dir)
    print(f"  机台={data.m} 订单={data.n} 配方={len(data.recipes)} "
          f"Σp={sum(data.p)} horizon_ub={data.horizon_ub()}")
    feasibility_check(data)

    print(f"=== 求解 (λ={lam}) ===")
    result = solve(data, lam, time_budget=args.time, seed=args.seed)

    # 输出 JSON
    os.makedirs(args.out, exist_ok=True)
    tag = os.path.basename(os.path.normpath(args.data_dir))
    out_json = os.path.join(args.out, f"{tag}_result.json")
    payload = {
        "data_dir": args.data_dir,
        "lambda": list(lam),
        "status": result["status"],
        "solver": result["solver"],
        "makespan": result["makespan"],
        "tardiness": result["tardiness"],
        "completion": result["completion"],
        "objective": result["objective"],
        "gap": result["gap"],
        "solve_time_s": result["solve_time_s"],
        "num_orders": data.n,
        "num_machines": data.m,
    }
    if result.get("schedule") is not None:
        sched = result["schedule"]
        payload["schedule"] = [
            {"order_id": data.orders[j].id,
             "machine_id": data.machines[sched.assignment[j]].id,
             "recipe_id": data.rho[j],
             "start": sched.start[j], "end": sched.end[j],
             "tardiness": max(0, sched.end[j] - data.d[j]),
             "priority": data.orders[j].priority}
            for j in range(data.n)
        ]
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(f"结果已写入: {out_json}")

    # 可视化
    if result.get("schedule") is not None and not args.no_viz:
        viz_dir = os.path.join(args.out, tag)
        paths = visualize.visualize(data, result["schedule"], viz_dir)
        for k, v in paths.items():
            print(f"  可视化[{k}]: {v}")

    print(f"=== 完成: status={result['status']} "
          f"makespan={result['makespan']} ΣT={result['tardiness']} "
          f"ΣC={result['completion']} time={result['solve_time_s']:.2f}s ===")


if __name__ == "__main__":
    main()
