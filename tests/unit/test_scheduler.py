"""单元测试：数据模型、评估、构造启发式、ALNS、CP-SAT 精确、路由。

运行: python -m pytest tests/unit/ -v
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

import pytest

from scheduler.model import (DataModel, DataError, evaluate, feasibility_check,
                             load_data)
from scheduler import cp_sat, heuristics, router

BASE = "/Users/tangmengzhang/Downloads/2026/OR_Course_2026_SO/Zen老师大作业/mip_course/data"
LAM = (0.0, 1.0, 0.0)  # tardiness 单目标


# ---------------------------------------------------------------------------
# 数据加载与体检
# ---------------------------------------------------------------------------

class TestLoadData:
    def test_load_toy(self):
        d = load_data(f"{BASE}/toy")
        assert d.n == 5
        assert d.m == 3
        assert sum(d.p) == 200
        assert len(d.recipes) == 3
        assert d.max_switch > 0

    def test_load_boundary_null_switch(self):
        d = load_data(f"{BASE}/boundary")
        nulls = sum(1 for v in d.switch.values() if v is None)
        assert nulls == 8  # boundary 4x4 含 8 个 null

    def test_empty_orders(self, tmp_path):
        (tmp_path / "machines.json").write_text("[]", encoding="utf-8")
        (tmp_path / "orders.json").write_text("[]", encoding="utf-8")
        (tmp_path / "recipes.json").write_text("[]", encoding="utf-8")
        (tmp_path / "switch_matrix.json").write_text(
            '{"recipes": [], "matrix": []}', encoding="utf-8")
        with pytest.raises(DataError):
            load_data(str(tmp_path))

    def test_missing_file(self, tmp_path):
        with pytest.raises(DataError):
            load_data(str(tmp_path))

    def test_bad_json(self, tmp_path):
        (tmp_path / "machines.json").write_text("{bad json", encoding="utf-8")
        with pytest.raises(DataError):
            load_data(str(tmp_path))


class TestFeasibility:
    def test_toy_feasible(self):
        d = load_data(f"{BASE}/toy")
        feasibility_check(d)  # 不应抛异常

    def test_boundary_feasible(self):
        d = load_data(f"{BASE}/boundary")
        feasibility_check(d)


# ---------------------------------------------------------------------------
# 评估函数
# ---------------------------------------------------------------------------

class TestEvaluate:
    def test_evaluate_consistency(self):
        d = load_data(f"{BASE}/toy")
        s0 = heuristics.constructive(d, LAM, seed=0)
        assert s0.feasible
        # makespan = max end
        assert s0.makespan == max(s0.end)
        # tardiness = Σ max(0, C_j - d_j)
        assert s0.tardiness == sum(max(0, s0.end[j] - d.d[j]) for j in range(d.n))
        # completion = Σ C_j
        assert s0.completion == sum(s0.end[j] for j in range(d.n))

    def test_evaluate_null_switch_infeasible(self):
        d = load_data(f"{BASE}/boundary")
        # 手工构造一个 null 切换序列：r1→r2 之间若有 null 则不可行
        # boundary switch: 检查是否存在 null 配方对，构造违反序列
        null_pair = next(((u, v) for (u, v), s in d.switch.items() if s is None), None)
        if null_pair:
            u, v = null_pair
            # 找配方 u 的订单和配方 v 的订单
            ju = next((j for j in range(d.n) if d.rho[j] == u), None)
            jv = next((j for j in range(d.n) if d.rho[j] == v), None)
            if ju is not None and jv is not None:
                mm = next(mm for mm in range(d.m)
                          if d.compatible[ju][mm] and d.compatible[jv][mm])
                seq = [ju, jv]
                sequences = [[] for _ in range(d.m)]
                sequences[mm] = seq
                assignment = [-1] * d.n
                assignment[ju] = mm
                assignment[jv] = mm
                sched = evaluate(d, assignment, sequences, LAM)
                assert not sched.feasible


# ---------------------------------------------------------------------------
# 构造启发式
# ---------------------------------------------------------------------------

class TestConstructive:
    def test_toy_feasible(self):
        d = load_data(f"{BASE}/toy")
        s0 = heuristics.constructive(d, LAM, seed=0)
        assert s0 is not None and s0.feasible
        # 每订单恰好分配
        assert all(0 <= s0.assignment[j] < d.m for j in range(d.n))

    def test_boundary_feasible(self):
        d = load_data(f"{BASE}/boundary")
        s0 = heuristics.constructive(d, LAM, seed=0)
        assert s0 is not None and s0.feasible

    def test_different_lambda_keys(self):
        d = load_data(f"{BASE}/toy")
        # 三种目标各跑一次，均应可行
        for lam in [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]:
            s0 = heuristics.constructive(d, lam, seed=0)
            assert s0 is not None and s0.feasible


# ---------------------------------------------------------------------------
# ALNS
# ---------------------------------------------------------------------------

class TestALNS:
    def test_alns_improves_or_keeps(self):
        d = load_data(f"{BASE}/toy")
        s0 = heuristics.constructive(d, LAM, seed=0)
        best = heuristics.alns(d, s0, LAM, time_limit=2.0, seed=42, verbose=False)
        assert best.feasible
        # ALNS 不应比初解差
        assert best.tardiness <= s0.tardiness


# ---------------------------------------------------------------------------
# CP-SAT 精确求解
# ---------------------------------------------------------------------------

class TestCpSat:
    def test_l1_optimal(self):
        d = load_data(f"{BASE}/toy")
        r = cp_sat.solve(d, LAM, time_limit=None, verbose=False)
        assert r["status"] == "OPTIMAL"
        assert r["makespan"] == 90
        assert r["tardiness"] == 82
        assert r["completion"] == 254
        assert r["gap"] == 0.0

    def test_l2_optimal(self):
        d = load_data(f"{BASE}/boundary")
        r = cp_sat.solve(d, LAM, time_limit=None, verbose=False)
        assert r["status"] == "OPTIMAL"
        assert r["makespan"] == 570
        assert r["tardiness"] == 1270


# ---------------------------------------------------------------------------
# 求解器路由
# ---------------------------------------------------------------------------

class TestRouter:
    def test_route_small_cp_sat(self):
        d = load_data(f"{BASE}/toy")
        r = router.solve(d, LAM, seed=42, verbose=False)
        assert r["solver"] == "CP-SAT"
        assert r["status"] == "OPTIMAL"

    def test_route_medium_metaheuristic(self):
        d = load_data(f"{BASE}/medium")
        r = router.solve(d, LAM, time_budget=5.0, seed=42, verbose=False)
        assert "ALNS" in r["solver"]
        assert r["status"] == "FEASIBLE"
