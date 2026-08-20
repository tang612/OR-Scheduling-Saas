"""
三机并行车间调度（makespan 最小化）— P_3 | chains | C_max
OR-Expert 交付: 公式编号 (1)-(6) 与模型一一对应
- (1) 目标 min C_max  (2) 工序链  (3) 机器分配  (4) NoOverlap  (5) makespan  (6) 变量域
时间单位: 小时 ×10 整数
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from ortools.sat.python import cp_model

# ---------- 数据（小时 ×10 整数化） ----------
JOBS = {  # 工件: [各工序加工时间 ×10]
    1: [20, 10, 20],
    2: [10, 10],
    3: [10, 5, 5, 10],
    4: [5, 5],
    5: [10, 5, 3, 15, 5],
    6: [5],
    7: [2, 3, 5, 2],
}
N_MACHINES = 3
HORIZON = sum(sum(ops) for ops in JOBS.values())  # 165: 总加工量上界

# ---------- 模型 ----------
m = cp_model.CpModel()
presence = {}    # presence[(j,k,m)]: 工序 (j,k) 是否在机器 m
intervals = {}   # intervals[(j,k,m)]: 可选区间
start_of = {}    # start_of[(j,k)]: 工序 (j,k) 开工时间（跨机器共享）
end_of = {}      # end_of[(j,k)]

for j, ops in JOBS.items():
    for k in range(len(ops)):
        s = m.NewIntVar(0, HORIZON, f"S_{j}_{k}")                      # (6) S_jk ≥ 0
        e = m.NewIntVar(0, HORIZON, f"E_{j}_{k}")                      # E_jk = S_jk + p_jk
        m.Add(e == s + ops[k])
        start_of[(j, k)], end_of[(j, k)] = s, e
        for mm in range(N_MACHINES):
            p_lit = m.NewBoolVar(f"y_{j}_{k}_{mm}")                    # (3) y_jkm
            presence[(j, k, mm)] = p_lit
            intervals[(j, k, mm)] = m.NewOptionalIntervalVar(
                s, ops[k], e, p_lit, f"int_{j}_{k}_{mm}")              # (4) 机器区间
        m.AddExactlyOne([presence[(j, k, mm)] for mm in range(N_MACHINES)])  # (3) Σ y_jkm = 1

# (4) 每台机器 NoOverlap: 同机区间两两不重叠
for mm in range(N_MACHINES):
    m.AddNoOverlap([intervals[(j, k, mm)] for j in JOBS for k in range(len(JOBS[j]))])

# (2) 工序链: S_j,k+1 ≥ E_j,k
for j, ops in JOBS.items():
    for k in range(len(ops) - 1):
        m.Add(start_of[(j, k + 1)] >= end_of[(j, k)])

# (1)(5) makespan: min C_max,  C_max ≥ E_j,n_j
Cmax = m.NewIntVar(0, HORIZON, "Cmax")
for j, ops in JOBS.items():
    m.Add(Cmax >= end_of[(j, len(ops) - 1)])
m.Minimize(Cmax)

# ---------- 求解 ----------
solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 30.0
status = solver.Solve(m)
assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE), f"status={status}"
print(f"[CP-SAT] status={'OPTIMAL' if status == cp_model.OPTIMAL else 'FEASIBLE'}")
print(f"[结果] 最优 makespan C_max = {solver.Value(Cmax)} (×10 分钟) = {solver.Value(Cmax)/10} 小时")

# ---------- 结果明细 ----------
machine_ops = {mm: [] for mm in range(N_MACHINES)}
total_load = 0
for j, ops in JOBS.items():
    for k in range(len(ops)):
        mm = next(x for x in range(N_MACHINES) if solver.Value(presence[(j, k, x)]) == 1)
        s, e = solver.Value(start_of[(j, k)]), solver.Value(end_of[(j, k)])
        machine_ops[mm].append((j, k, s, e))
        total_load += ops[k]
        print(f"  J{j} 工序{k+1}: 机器M{mm+1}  开工={s/10}h  完工={e/10}h  (时长{ops[k]/10}h)")

print("\n[机器负载]")
for mm in range(N_MACHINES):
    load = sum(e - s for _, _, s, e in machine_ops[mm])
    print(f"  M{mm+1}: {len(machine_ops[mm])} 道工序, 负载 {load/10}h ({load/total_load*100:.0f}%)")

# ---------- 甘特图 ----------
for f in ["/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"]:
    try:
        fm.fontManager.addfont(f)
    except Exception:
        pass
plt.rcParams["font.family"] = ["STHeiti", "Hiragino Sans GB", "sans-serif"]
colors = plt.cm.tab10.colors
fig, ax = plt.subplots(figsize=(12, 4.2), dpi=200)
for mm in range(N_MACHINES):
    for j, k, s, e in machine_ops[mm]:
        ax.barh(N_MACHINES - mm, (e - s) / 10, left=s / 10, height=0.6,
                color=colors[j % 10], edgecolor="white")
        ax.text((s + e) / 20, N_MACHINES - mm, f"J{j}-{k+1}", ha="center", va="center",
                fontsize=8, color="white", fontweight="bold")
ax.set_yticks([3, 2, 1])
ax.set_yticklabels(["M1", "M2", "M3"])
ax.set_xlabel("时间（小时）")
ax.set_title(f"最优调度甘特图（makespan = {solver.Value(Cmax)/10} 小时）", fontsize=13)
ax.set_xlim(0, solver.Value(Cmax) / 10 + 0.5)
ax.grid(axis="x", alpha=0.3)
fig.tight_layout()
fig.savefig("docs/parallel_machines_gantt.png", dpi=200, facecolor="white")
plt.close(fig)
print("\n甘特图已生成: docs/parallel_machines_gantt.png")
