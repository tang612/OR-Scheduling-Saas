"""生成单机加权完工时间问题的结果可视化（甘特图 + 全排列目标值对比）。
输出: docs/wct_gantt.png, docs/wct_compare.png（供过程报告嵌入）"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from itertools import permutations

# 中文字体
for f in ["/System/Library/Fonts/STHeiti Medium.ttc",
          "/System/Library/Fonts/Hiragino Sans GB.ttc"]:
    try:
        fm.fontManager.addfont(f)
    except Exception:
        pass
plt.rcParams["font.family"] = ["STHeiti", "Hiragino Sans GB", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

JOBS = {1: (2, 3), 2: (3, 1), 3: (1, 2)}   # j: (p, w)

# ---------- 最优顺序（WSPT: p/w 升序）----------
order = sorted(JOBS, key=lambda j: JOBS[j][0] / JOBS[j][1])  # J3→J1→J2

# ---------- 图1: 甘特图 ----------
fig, ax = plt.subplots(figsize=(9, 2.8), dpi=200)
colors = {1: "#4a6cf7", 2: "#e67e22", 3: "#27ae60"}
t = 0
for j in order:
    p, w = JOBS[j]
    ax.barh(0, p, left=t, height=0.5, color=colors[j], edgecolor="white")
    ax.text(t + p / 2, 0, f"J{j}\n({p}h, w={w})", ha="center", va="center",
            color="white", fontsize=11, fontweight="bold")
    ax.text(t + p + 0.03, 0.32, f"C={t+p}", fontsize=9, color="#333")
    t += p
ax.set_xlim(0, 7)
ax.set_ylim(-0.55, 0.75)
ax.set_yticks([])
ax.set_xlabel("时间（小时）")
ax.set_title("最优加工顺序: J3 → J1 → J2（WSPT 规则）", fontsize=13)
ax.grid(axis="x", alpha=0.3)
fig.tight_layout()
fig.savefig("docs/wct_gantt.png", dpi=200, facecolor="white")
plt.close(fig)

# ---------- 图2: 全排列目标值对比 ----------
results = []
for perm in permutations(JOBS):
    t, val = 0, 0
    for j in perm:
        t += JOBS[j][0]
        val += JOBS[j][1] * t
    results.append(("".join(f"J{j}" for j in perm), val))
results.sort(key=lambda x: x[1])

fig, ax = plt.subplots(figsize=(9, 3.6), dpi=200)
labels = [r[0] for r in results]
vals = [r[1] for r in results]
colors_bar = ["#27ae60" if v == min(vals) else "#b0b8c8" for v in vals]
bars = ax.bar(labels, vals, color=colors_bar, edgecolor="white")
for b, v in zip(bars, vals):
    ax.text(b.get_x() + b.get_width() / 2, v + 0.3, str(v), ha="center", fontsize=11)
ax.set_ylabel("Σ w_j C_j（加权完工时间总和）")
ax.set_title("6 种排列目标值对比（最优 = 17）", fontsize=13)
ax.set_ylim(0, max(vals) * 1.15)
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig("docs/wct_compare.png", dpi=200, facecolor="white")
plt.close(fig)
print("可视化已生成: docs/wct_gantt.png, docs/wct_compare.png")
