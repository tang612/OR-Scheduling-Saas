"""
1||Σw_jC_j 单机加权完工时间最小化 — OR-Expert 四件套交付
公式编号映射: (1)目标  (2)(3)指派约束  (4)完工时间递推
验证: WSPT 解析解 + 全排列穷举 (L1 玩具用例, 3!=6 手工可算)
"""
from itertools import permutations
from ortools.sat.python import cp_model

# ---------- 数据 ----------
JOBS = {1: {"p": 2, "w": 3}, 2: {"p": 3, "w": 1}, 3: {"p": 1, "w": 2}}
J = list(JOBS)          # 作业集合 J
K = list(range(1, len(J) + 1))  # 位置集合 K
p = {j: JOBS[j]["p"] for j in J}
w = {j: JOBS[j]["w"] for j in J}

# ---------- CP-SAT 模型 ----------
m = cp_model.CpModel()

# 决策变量 x[j][k] ∈ {0,1}: 作业 j 排在第 k 位
x = {j: {k: m.NewBoolVar(f"x_{j}_{k}") for k in K} for j in J}          # (1)-(4) 共用

for j in J:
    m.Add(sum(x[j][k] for k in K) == 1)                                  # (2) 每作业恰一位
for k in K:
    m.Add(sum(x[j][k] for j in J) == 1)                                  # (3) 每位置恰一作业

C = {k: m.NewIntVar(0, sum(p.values()), f"C_{k}") for k in K}            # (4) 位置 k 完工时间
for k in K:
    m.Add(C[k] == sum(p[j] * x[j][l] for l in range(1, k + 1) for j in J))  # (4) 累计加工时间

W = {k: m.NewIntVar(0, max(w.values()), f"W_{k}") for k in K}            # (5) 位置 k 的作业权重
for k in K:
    m.Add(W[k] == sum(w[j] * x[j][k] for j in J))                        # (5) W_k = Σ w_j·x_jk
Z = {k: m.NewIntVar(0, sum(p.values()) * max(w.values()), f"Z_{k}") for k in K}  # (6) 乘积辅助
for k in K:
    m.AddMultiplicationEquality(Z[k], C[k], W[k])                        # (6) Z_k = C_k · W_k
m.Minimize(sum(Z.values()))                                              # (1') 目标: min Σ Z_k

# ---------- 求解 ----------
solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 10.0
status = solver.Solve(m)
assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE), f"solve failed: {status}"

order = [j for k in K for j in J if solver.Value(x[j][k]) == 1]          # 最优顺序
obj = solver.ObjectiveValue()
print(f"[CP-SAT] 最优顺序: {' → '.join(f'J{j}' for j in order)}  目标值: {obj}")

# ---------- 交叉验证 1: WSPT 解析解 (p/w 升序) ----------
wspt = sorted(J, key=lambda j: p[j] / w[j])
t = 0
wspt_val = 0
for j in wspt:
    t += p[j]
    wspt_val += w[j] * t
print(f"[WSPT ] 解析顺序: {' → '.join(f'J{j}' for j in wspt)}  目标值: {wspt_val}")
assert order == wspt, "CP-SAT 解与 WSPT 不一致!"
assert abs(obj - wspt_val) < 1e-6, "目标值不一致!"

# ---------- 交叉验证 2: 全排列穷举 (L1 玩具用例) ----------
best_val, best_seq = float("inf"), None
for perm in permutations(J):
    t, val = 0, 0
    for j in perm:
        t += p[j]
        val += w[j] * t
    if val < best_val:
        best_val, best_seq = val, perm
print(f"[穷举 ] 最优顺序: {' → '.join(f'J{j}' for j in best_seq)}  目标值: {best_val}")
assert best_val == obj, "穷举与 CP-SAT 不一致!"

# ---------- 输出每个作业完工时间 ----------
t = 0
for j in order:
    t += p[j]
    print(f"  作业 J{j}: 完工时间 C_j = {t} 小时 (加权贡献 {w[j]}×{t} = {w[j]*t})")

print(f"\n[L1 测试] 三项交叉验证全部通过 ✅  Σw_jC_j = {int(obj)}")
