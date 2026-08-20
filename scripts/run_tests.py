#!/usr/bin/env python3
"""L1-L4 四层测试：求解 + 自动约束验证 + 生成测试报告。

用法: python3 scripts/run_tests.py [--levels toy,boundary,medium,large]
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "solver-core"))
from scheduler.model import load_data, feasibility_check
from scheduler.router import solve
from scheduler import visualize

BASE = "/Users/tangmengzhang/Downloads/2026/OR_Course_2026_SO/Zen老师大作业/mip_course/data"
LEVELS = {
    "toy":      ("L1", "玩具用例 · 手工可验证", "必须给出正确解"),
    "boundary": ("L2", "边界用例 · 高不可切换比例", "不崩溃，null 正确处理"),
    "medium":   ("L3", "中等规模性能", "5 分钟内出解"),
    "large":    ("L4", "大规模压力", "15 分钟内出解"),
    "massive":  ("L5", "极限压力", "可用解（本阶段跳过）"),
}


def verify(data, sched, lambda_):
    """自动验证解的正确性：分配/兼容/NoOverlap/切换/延误/目标。返回错误列表。"""
    errors = []
    n, m = data.n, data.m
    assign = sched.assignment

    # 1. 每订单恰一台机台 + 兼容
    for j in range(n):
        mm = assign[j]
        if mm < 0 or mm >= m:
            errors.append(f"订单 {j}({data.orders[j].id}) 未分配机台")
        elif not data.compatible[j][mm]:
            errors.append(f"订单 {j} 配方 {data.rho[j]} 分配到不兼容机台 {data.machines[mm].id}")

    # 2. NoOverlap + 3. 切换时间
    for mm in range(m):
        seq = sched.sequences[mm]
        intervals = sorted((sched.start[j], sched.end[j]) for j in seq)
        for a, b in zip(intervals, intervals[1:]):
            if a[1] > b[0]:
                errors.append(f"机台 {data.machines[mm].id} 订单重叠 {a} vs {b}")
        for prev, cur in zip(seq, seq[1:]):
            s_val = data.switch.get((data.rho[prev], data.rho[cur]))
            if s_val is None:
                errors.append(f"机台 {data.machines[mm].id} 出现 null 切换 {data.rho[prev]}→{data.rho[cur]}")
            else:
                need = sched.end[prev] + s_val + data.machines[mm].cleanup_time
                if need > sched.start[cur]:
                    errors.append(f"机台 {data.machines[mm].id} 切换时间不足: "
                                  f"需 {need} 实际 {sched.start[cur]}")

    # 4. 延误/完工一致性
    for j in range(n):
        if sched.end[j] != sched.start[j] + data.p[j]:
            errors.append(f"订单 {j} 完工≠开工+加工")

    # 5. 目标分量一致性
    exp_tard = sum(max(0, sched.end[j] - data.d[j]) for j in range(n))
    if exp_tard != sched.tardiness:
        errors.append(f"ΣT 不一致: 计算 {exp_tard} vs 记录 {sched.tardiness}")
    exp_comp = sum(sched.end[j] for j in range(n))
    if exp_comp != sched.completion:
        errors.append(f"ΣC 不一致: 计算 {exp_comp} vs 记录 {sched.completion}")
    exp_mk = max(sched.end[j] for j in range(n))
    if exp_mk != sched.makespan:
        errors.append(f"makespan 不一致: 计算 {exp_mk} vs 记录 {sched.makespan}")

    return errors


def run_one(data_dir, level_key, lam, out_dir, seed, time_budget=None):
    tag = level_key
    print(f"\n{'='*60}\n[{LEVELS[tag][0]}] {LEVELS[tag][1]} → {data_dir}\n{'='*60}")
    try:
        data = load_data(data_dir)
    except Exception as e:
        return {"level": LEVELS[tag][0], "name": LEVELS[tag][1],
                "status": "LOAD_ERROR", "error": str(e)}
    feasibility_check(data)
    print(f"  机台={data.m} 订单={data.n} Σp={sum(data.p)} "
          f"null切换={sum(1 for v in data.switch.values() if v is None)}")

    result = solve(data, lam, time_budget=time_budget, seed=seed)
    errors = []
    if result.get("schedule") is not None:
        errors = verify(data, result["schedule"], lam)

    # 可视化
    viz_paths = {}
    if result.get("schedule") is not None:
        viz_dir = os.path.join(out_dir, tag)
        try:
            viz_paths = visualize.visualize(data, result["schedule"], viz_dir)
        except Exception as e:
            print(f"  [可视化失败] {e}")

    ok = (result.get("status") in ("OPTIMAL", "FEASIBLE")) and not errors
    print(f"  结果: status={result.get('status')} makespan={result.get('makespan')} "
          f"ΣT={result.get('tardiness')} ΣC={result.get('completion')} "
          f"time={result.get('solve_time_s',0):.2f}s gap={result.get('gap')}")
    print(f"  约束验证: {'✓ 通过' if not errors else '✗ ' + str(len(errors)) + ' 错误'}")
    for e in errors[:10]:
        print(f"    - {e}")

    return {
        "level": LEVELS[tag][0], "name": LEVELS[tag][1],
        "accept": LEVELS[tag][2], "data_dir": data_dir,
        "status": result.get("status"), "solver": result.get("solver"),
        "makespan": result.get("makespan"), "tardiness": result.get("tardiness"),
        "completion": result.get("completion"), "objective": result.get("objective"),
        "gap": result.get("gap"), "solve_time_s": result.get("solve_time_s"),
        "num_orders": result.get("num_orders", data.n if 'data' in dir() else None),
        "num_machines": data.m, "lambda": list(lam),
        "verify_errors": errors, "viz": viz_paths,
        "ok": ok,
    }


def write_report(entry, out_dir):
    tag = entry["level"]
    fname = os.path.join(out_dir, f"test_{tag}.md")
    err = entry.get("verify_errors", [])
    with open(fname, "w", encoding="utf-8") as fh:
        fh.write(f"# {entry['level']} 测试报告 · {entry['name']}\n\n")
        fh.write(f"- 验收标准：{entry['accept']}\n")
        fh.write(f"- 数据目录：`{entry['data_dir']}`\n\n")
        fh.write("## 求解结果\n\n")
        fh.write("| 指标 | 值 |\n|---|---|\n")
        for k in ("status", "solver", "makespan", "tardiness", "completion",
                  "objective", "gap", "solve_time_s", "num_machines"):
            v = entry.get(k)
            if v is not None:
                fh.write(f"| {k} | {v} |\n")
        fh.write(f"| num_orders | {entry.get('num_orders', '-')} |\n")
        fh.write(f"| λ | {entry.get('lambda')} |\n\n")
        fh.write("## 约束验证（自动）\n\n")
        if err:
            fh.write(f"❌ **发现 {len(err)} 处错误**：\n\n")
            for e in err:
                fh.write(f"- {e}\n")
        else:
            fh.write("✓ 全部通过：每订单恰一机台、机器-配方兼容、NoOverlap、切换+清理时间、延误/完工/目标一致性。\n")
        fh.write(f"\n## 结论\n\n**{'✓ 通过' if entry.get('ok') else '✗ 未通过'}** "
                 f"（status={entry.get('status')}，验证{'通过' if not err else '失败'}）\n")
    return fname


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", default="toy,boundary,medium,large",
                    help="逗号分隔：toy,boundary,medium,large")
    ap.add_argument("--lambda", dest="lam", default="0,1,0")
    ap.add_argument("--out", default="docs/test_reports")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    lam = tuple(float(x) for x in args.lam.split(","))
    os.makedirs(args.out, exist_ok=True)
    out_dir = os.path.abspath(args.out)
    viz_base = os.path.join(os.path.dirname(out_dir), "results")

    entries = []
    for tag in args.levels.split(","):
        tag = tag.strip()
        if tag not in LEVELS:
            continue
        if tag == "massive":
            print(f"[跳过] L5 massive（本阶段不测试）")
            continue
        entry = run_one(os.path.join(BASE, tag), tag, lam, viz_base, args.seed)
        entries.append(entry)
        write_report(entry, out_dir)
        print(f"  报告已写入: {os.path.join(out_dir, 'test_' + entry['level'] + '.md')}")

    # 汇总
    summary = os.path.join(out_dir, "summary.md")
    with open(summary, "w", encoding="utf-8") as fh:
        fh.write("# L1-L4 测试汇总\n\n")
        fh.write("| 层级 | 状态 | 求解器 | makespan | ΣT | ΣC | 耗时(s) | gap | 验证 |\n")
        fh.write("|---|---|---|---|---|---|---|---|---|\n")
        for e in entries:
            fh.write(f"| {e['level']} | {e.get('status')} | {e.get('solver')} | "
                     f"{e.get('makespan')} | {e.get('tardiness')} | {e.get('completion')} | "
                     f"{e.get('solve_time_s',0):.2f} | {e.get('gap')} | "
                     f"{'✓' if not e.get('verify_errors') else '✗'} |\n")
        all_ok = all(e.get("ok") for e in entries)
        fh.write(f"\n**总判定：{'✓ 全部通过' if all_ok else '✗ 存在未通过项'}**\n")
    print(f"\n汇总报告: {summary}")


if __name__ == "__main__":
    main()
