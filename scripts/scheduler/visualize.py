"""分层可视化（V1~V3 已确认）。

- L1/L2：甘特图（手工验证）
- L3：负载图 + 延误散点
- L4/L5：负载堆叠图 + 时间热力图 + 延误散点 + KPI（甘特图仅瓶颈下钻）
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np

from .model import DataModel, Schedule

# 中文字体
for _f in ["/System/Library/Fonts/STHeiti Medium.ttc",
           "/System/Library/Fonts/Hiragino Sans GB.ttc",
           "/System/Library/Fonts/PingFang.ttc"]:
    try:
        fm.fontManager.addfont(_f)
    except Exception:
        pass
plt.rcParams["font.family"] = ["STHeiti", "Hiragino Sans GB", "PingFang SC", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

COLORS = plt.cm.tab10.colors
STATE_COLORS = {"加工": "#4a6cf7", "切换": "#e67e22", "空闲": "#e8e8e8"}


def _machine_loads(data: DataModel, sched: Schedule):
    """每机台 加工/切换/空闲 三段时长。"""
    rows = []
    for mm in range(data.m):
        proc = sum(data.p[j] for j in sched.sequences[mm])
        setup = 0
        t = 0
        last = None
        for j in sched.sequences[mm]:
            if last is not None:
                setup += data.switch.get((last, data.rho[j]), 0) + data.machines[mm].cleanup_time
            t = sched.end[j]
            last = data.rho[j]
        idle = sched.makespan - proc - setup
        rows.append((data.machines[mm].id, proc, setup, idle))
    return rows


def plot_load(data: DataModel, sched: Schedule, path: str):
    """机器负载堆叠图（主视图）。"""
    rows = _machine_loads(data, sched)
    ids = [r[0] for r in rows]
    proc = [r[1] for r in rows]
    setup = [r[2] for r in rows]
    idle = [r[3] for r in rows]
    y = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(max(6, len(rows) * 0.35), 5), dpi=150)
    ax.barh(y, proc, color=STATE_COLORS["加工"], label="加工")
    ax.barh(y, setup, left=proc, color=STATE_COLORS["切换"], label="切换+清理")
    ax.barh(y, idle, left=[a + b for a, b in zip(proc, setup)],
            color=STATE_COLORS["空闲"], label="空闲")
    ax.set_yticks(y)
    ax.set_yticklabels(ids)
    ax.set_xlabel("时间")
    ax.set_title(f"机器负载（makespan={sched.makespan}）")
    ax.legend(loc="lower right", ncol=3, fontsize=8)
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor="white")
    plt.close(fig)


def plot_heatmap(data: DataModel, sched: Schedule, path: str):
    """时间-机器热力图：颜色 = 配方类型。"""
    m = data.m
    fig, ax = plt.subplots(figsize=(12, max(4, m * 0.35)), dpi=150)
    recipe_ids = sorted({data.rho[j] for j in range(data.n)})
    cmap = matplotlib.colormaps["tab20"].resampled(len(recipe_ids))
    ridx = {r: i for i, r in enumerate(recipe_ids)}
    for mm in range(m):
        for j in sched.sequences[mm]:
            ax.barh(m - mm, data.p[j], left=sched.start[j], height=0.7,
                    color=cmap(ridx[data.rho[j]]), edgecolor="white")
    ax.set_yticks([m - mm for mm in range(m)])
    ax.set_yticklabels([data.machines[mm].id for mm in range(m)])
    ax.set_xlabel("时间")
    ax.set_title("时间-机器热力图（颜色=配方）")
    ax.set_xlim(0, sched.makespan * 1.02)
    # 图例
    import matplotlib.patches as mpatches
    handles = [mpatches.Patch(color=cmap(ridx[r]), label=r) for r in recipe_ids]
    ax.legend(handles=handles, loc="upper right", fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor="white")
    plt.close(fig)


def plot_due_scatter(data: DataModel, sched: Schedule, path: str):
    """完工 vs 交期散点图（对角线=准点线）。"""
    d = [data.d[j] for j in range(data.n)]
    c = [sched.end[j] for j in range(data.n)]
    fig, ax = plt.subplots(figsize=(7, 6), dpi=150)
    mx = max(max(d), max(c)) * 1.05
    ax.plot([0, mx], [0, mx], "k--", lw=1, alpha=0.5, label="准点线")
    on_time = sum(1 for j in range(data.n) if c[j] <= d[j])
    ax.scatter(d, c, s=18, alpha=0.6,
               c=["#2ecc71" if c[j] <= d[j] else "#e74c3c" for j in range(data.n)])
    ax.set_xlabel("交期 d_j")
    ax.set_ylabel("完工 C_j")
    ax.set_title(f"完工 vs 交期（准点率 {on_time}/{data.n}）")
    ax.legend()
    ax.set_xlim(0, mx)
    ax.set_ylim(0, mx)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor="white")
    plt.close(fig)


def plot_gantt(data: DataModel, sched: Schedule, path: str, max_machines: int = 20):
    """甘特图（L1/L2 全量，L4/L5 仅瓶颈下钻）。"""
    m = data.m
    fig, ax = plt.subplots(figsize=(max(8, sched.makespan / 40), max(3, m * 0.5)), dpi=150)
    recipe_ids = sorted({data.rho[j] for j in range(data.n)})
    ridx = {r: i for i, r in enumerate(recipe_ids)}
    cmap = matplotlib.colormaps["tab20"].resampled(len(recipe_ids))
    for mm in range(m):
        for j in sched.sequences[mm]:
            ax.barh(m - mm, data.p[j], left=sched.start[j], height=0.65,
                    color=cmap(ridx[data.rho[j]]), edgecolor="white")
            ax.text(sched.start[j] + data.p[j] / 2, m - mm, j if data.n <= 12 else "",
                    ha="center", va="center", fontsize=7, color="white", fontweight="bold")
    ax.set_yticks([m - mm for mm in range(m)])
    ax.set_yticklabels([data.machines[mm].id for mm in range(m)])
    ax.set_xlabel("时间")
    ax.set_title(f"调度甘特图（makespan={sched.makespan}）")
    ax.set_xlim(0, sched.makespan * 1.02)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor="white")
    plt.close(fig)


def visualize(data: DataModel, sched: Schedule, out_dir: str, tag: str = "") -> dict:
    """按规模生成对应可视化，返回图片路径 dict。"""
    import os
    os.makedirs(out_dir, exist_ok=True)
    prefix = f"{tag}_" if tag else ""
    n = data.n
    paths = {}

    if n <= 12:
        p = os.path.join(out_dir, f"{prefix}gantt.png")
        plot_gantt(data, sched, p)
        paths["gantt"] = p
    elif n <= 50:
        p = os.path.join(out_dir, f"{prefix}load.png")
        plot_load(data, sched, p)
        paths["load"] = p
        p2 = os.path.join(out_dir, f"{prefix}due.png")
        plot_due_scatter(data, sched, p2)
        paths["due"] = p2
    else:
        p = os.path.join(out_dir, f"{prefix}load.png")
        plot_load(data, sched, p)
        paths["load"] = p
        p2 = os.path.join(out_dir, f"{prefix}heatmap.png")
        plot_heatmap(data, sched, p2)
        paths["heatmap"] = p2
        p3 = os.path.join(out_dir, f"{prefix}due.png")
        plot_due_scatter(data, sched, p3)
        paths["due"] = p3
    return paths
