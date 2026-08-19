#!/usr/bin/env python3
"""算法迭代优化实验：baseline（构造）→ 原 ALNS → 优化 ALNS（多指标引导 + 智能终止）。

生成：收敛曲线 + 指标对比图 + 迭代追溯快照 + HTML 报告。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from scheduler.model import load_data, feasibility_check
from scheduler import heuristics, evaluation

BASE = "/Users/tangmengzhang/Downloads/2026/OR_Course_2026_SO/Zen老师大作业/mip_course/data"
LAM = (0.0, 1.0, 0.0)  # tardiness 单目标
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
VIZ_DIR = os.path.join(OUT, "results", "iteration")


def run_experiment(tag="medium", time_limit=20.0, seed=42, w_bal=0.15, w_flex=0.15):
    data = load_data(f"{BASE}/{tag}")
    feasibility_check(data)
    print(f"=== {tag}: n={data.n} m={data.m} Σp={sum(data.p)} ===")

    # 1. baseline：构造启发式（EDD）
    t0 = time.time()
    s_base = heuristics.constructive(data, LAM, seed=seed)
    t_base = time.time() - t0
    print(f"  [baseline] 构造: makespan={s_base.makespan} ΣT={s_base.tardiness}")

    # 2. 原 ALNS（纯 λ 目标）
    t0 = time.time()
    s_alns, hist_alns = heuristics.alns(
        data, s_base, LAM, time_limit=time_limit, seed=seed,
        verbose=False, return_history=True)
    t_alns = time.time() - t0
    print(f"  [原ALNS] makespan={s_alns.makespan} ΣT={s_alns.tardiness} time={t_alns:.1f}s")

    # 3. 优化 ALNS（多指标引导 + 相对改进率终止）
    t0 = time.time()
    s_opt, hist_opt = heuristics.alns(
        data, s_base, LAM, time_limit=time_limit, seed=seed, verbose=False,
        w_bal=w_bal, w_flex=w_flex, imp_patience=2000, imp_threshold=1e-6,
        return_history=True)
    t_opt = time.time() - t0
    print(f"  [优化ALNS] makespan={s_opt.makespan} ΣT={s_opt.tardiness} time={t_opt:.1f}s")

    # 4. 指标 + 评分
    ref = evaluation.lower_bound(data, LAM)
    m_base = evaluation.compute_metrics(data, s_base, LAM, reference=ref, solve_time=t_base)
    m_alns = evaluation.compute_metrics(data, s_alns, LAM, reference=ref, solve_time=t_alns)
    m_opt = evaluation.compute_metrics(data, s_opt, LAM, reference=ref, solve_time=t_opt)

    return {
        "data": data, "s_base": s_base, "s_alns": s_alns, "s_opt": s_opt,
        "hist_alns": hist_alns, "hist_opt": hist_opt,
        "m_base": m_base, "m_alns": m_alns, "m_opt": m_opt,
        "score_base": evaluation.compute_score(m_base),
        "score_alns": evaluation.compute_score(m_alns),
        "score_opt": evaluation.compute_score(m_opt),
        "t_base": t_base, "t_alns": t_alns, "t_opt": t_opt,
        "ref": ref,
    }


def make_plots(r, tag):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    for f in ["/System/Library/Fonts/STHeiti Medium.ttc",
              "/System/Library/Fonts/Hiragino Sans GB.ttc"]:
        try:
            fm.fontManager.addfont(f)
        except Exception:
            pass
    plt.rcParams["font.family"] = ["STHeiti", "Hiragino Sans GB", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False
    os.makedirs(VIZ_DIR, exist_ok=True)

    # 图 1：收敛曲线（ΣT 随迭代下降）
    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=150)
    for hist, label, color in [(r["hist_alns"], "原 ALNS（纯目标）", "#4a6cf7"),
                                (r["hist_opt"], "优化 ALNS（多指标引导）", "#e67e22")]:
        if hist:
            it = [h[0] for h in hist]
            obj = [h[1] for h in hist]
            ax.plot(it, obj, label=label, color=color, lw=1.5)
    ax.set_xlabel("迭代轮次")
    ax.set_ylabel("最优 ΣT（加权延误）")
    ax.set_title(f"收敛曲线对比（{tag}，目标=最小化 ΣT）")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p1 = os.path.join(VIZ_DIR, f"{tag}_convergence.png")
    fig.savefig(p1, dpi=150, facecolor="white")
    plt.close(fig)

    # 图 2：目标指标对比（makespan/ΣT/ΣC）
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    labels = ["makespan", "ΣT（延误）", "ΣC（完工）"]
    vals = {
        "baseline": [r["m_base"]["makespan"], r["m_base"]["tardiness"], r["m_base"]["completion"]],
        "原 ALNS": [r["m_alns"]["makespan"], r["m_alns"]["tardiness"], r["m_alns"]["completion"]],
        "优化 ALNS": [r["m_opt"]["makespan"], r["m_opt"]["tardiness"], r["m_opt"]["completion"]],
    }
    x = range(len(labels))
    width = 0.25
    for i, (name, v) in enumerate(vals.items()):
        ax.bar([xi + (i - 1) * width for xi in x], v, width, label=name)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("值")
    ax.set_title(f"目标指标对比（{tag}）")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    p2 = os.path.join(VIZ_DIR, f"{tag}_objectives.png")
    fig.savefig(p2, dpi=150, facecolor="white")
    plt.close(fig)

    # 图 3：质量指标对比（balance/flex/score）
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    labels2 = ["负载均衡", "可调整弹性", "综合评分"]
    vals2 = {
        "baseline": [r["m_base"]["balance"], r["m_base"]["flex"], r["score_base"]],
        "原 ALNS": [r["m_alns"]["balance"], r["m_alns"]["flex"], r["score_alns"]],
        "优化 ALNS": [r["m_opt"]["balance"], r["m_opt"]["flex"], r["score_opt"]],
    }
    x = range(len(labels2))
    for i, (name, v) in enumerate(vals2.items()):
        ax.bar([xi + (i - 1) * width for xi in x], v, width, label=name)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels2)
    ax.set_ylim(0, 1)
    ax.set_ylabel("值（0~1）")
    ax.set_title(f"质量指标对比（{tag}）")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    p3 = os.path.join(VIZ_DIR, f"{tag}_quality.png")
    fig.savefig(p3, dpi=150, facecolor="white")
    plt.close(fig)

    return p1, p2, p3


def make_snapshots(r, tag, w_bal=0.15, w_flex=0.15):
    """迭代追溯快照：v0 baseline → v1 原 ALNS → v2 优化 ALNS。"""
    config = {"lambda": list(LAM), "w_bal": w_bal, "w_flex": w_flex,
              "instance": tag, "seed": 42}
    reference = {"type": "lower_bound", "value": round(r["ref"], 2)}
    snaps = [
        evaluation.snapshot("v0", "构造启发式（EDD 基线）", "-", tag,
                            reference, config, r["m_base"], None),
        evaluation.snapshot("v1", "原 ALNS（纯 λ 目标）", "-", tag,
                            reference, config, r["m_alns"], r["m_base"]),
        evaluation.snapshot("v2", "优化 ALNS（多指标引导 + 智能终止）", "-", tag,
                            reference, config, r["m_opt"], r["m_alns"]),
    ]
    os.makedirs(VIZ_DIR, exist_ok=True)
    path = os.path.join(VIZ_DIR, f"{tag}_snapshots.json")
    evaluation.snapshots_to_json(snaps, path)
    return snaps, path


def build_report(r, tag, p1, p2, p3, snaps):
    """生成 report JSON（供 build_report.py 构建 HTML）。"""
    sections = [
        {"type": "heading", "level": 2, "text": "一、算法优化内容与方法"},
        {"type": "text", "text": "<b>优化前</b>：ALNS 接受准则 = 单一 λ 加权目标（λ1·Cmax+λ2·ΣT+λ3·ΣC），固定时间限制终止。"},
        {"type": "text", "text": "<b>优化后（方案 V3 三处改动）</b>：① 接受准则扩展为<b>多指标引导目标</b> obj/scale + w_bal·(1−balance) + w_flex·(1−flex)，将负载均衡与可调整弹性纳入搜索引导；② 新增<b>相对改进率终止</b>（连续 N 轮改进 < δ 即停，替代固定时间限制）；③ 每次迭代记录<b>收敛曲线</b>，支持量化/对比/追溯。"},
        {"type": "note", "text": "评测基准指标固定（makespan/ΣT/ΣC），算法引导目标可演化——「固定尺子量」，量出的进步才可对比。"},

        {"type": "heading", "level": 2, "text": "二、收敛曲线（ΣT 随迭代下降）"},
        {"type": "figure", "src": f"results/iteration/{tag}_convergence.png",
         "caption": "图 1：原 ALNS vs 优化 ALNS 的 ΣT 收敛曲线"},

        {"type": "heading", "level": 2, "text": "三、目标指标对比"},
        {"type": "figure", "src": f"results/iteration/{tag}_objectives.png",
         "caption": "图 2：makespan / ΣT / ΣC 三版本对比"},

        {"type": "heading", "level": 2, "text": "四、质量指标对比"},
        {"type": "figure", "src": f"results/iteration/{tag}_quality.png",
         "caption": "图 3：负载均衡 / 可调整弹性 / 综合评分 三版本对比"},

        {"type": "heading", "level": 2, "text": "五、指标明细与迭代追溯（delta）"},
        {"type": "table", "headers": ["指标", "baseline v0", "原 ALNS v1", "优化 ALNS v2", "v2−v1 增量"],
         "rows": [
            ["makespan", str(r["m_base"]["makespan"]), str(r["m_alns"]["makespan"]),
             str(r["m_opt"]["makespan"]),
             f"{r['m_opt']['makespan']-r['m_alns']['makespan']:+.0f}"],
            ["ΣT（延误）", str(r["m_base"]["tardiness"]), str(r["m_alns"]["tardiness"]),
             str(r["m_opt"]["tardiness"]),
             f"{r['m_opt']['tardiness']-r['m_alns']['tardiness']:+.0f}"],
            ["ΣC（完工）", str(r["m_base"]["completion"]), str(r["m_alns"]["completion"]),
             str(r["m_opt"]["completion"]),
             f"{r['m_opt']['completion']-r['m_alns']['completion']:+.0f}"],
            ["负载均衡", f"{r['m_base']['balance']:.4f}", f"{r['m_alns']['balance']:.4f}",
             f"{r['m_opt']['balance']:.4f}",
             f"{r['m_opt']['balance']-r['m_alns']['balance']:+.4f}"],
            ["可调整弹性", f"{r['m_base']['flex']:.4f}", f"{r['m_alns']['flex']:.4f}",
             f"{r['m_opt']['flex']:.4f}",
             f"{r['m_opt']['flex']-r['m_alns']['flex']:+.4f}"],
            ["耗时(s)", f"{r['t_base']:.2f}", f"{r['t_alns']:.2f}", f"{r['t_opt']:.2f}",
             f"{r['t_opt']-r['t_alns']:+.2f}"],
            ["综合评分", f"{r['score_base']:.4f}", f"{r['score_alns']:.4f}",
             f"{r['score_opt']:.4f}",
             f"{r['score_opt']-r['score_alns']:+.4f}"],
         ]},

        {"type": "heading", "level": 2, "text": "六、迭代追溯快照"},
        {"type": "code", "lang": "json",
         "code": json.dumps(snaps, ensure_ascii=False, indent=2)},

        {"type": "note", "text": "诚实声明：tardiness 目标绝对 gap 本质松（下界无法捕捉排队延误），故 gap 仅作保守报告；迭代进步以「综合评分 + 相对改进率」量化。快照完整 JSON 存 docs/results/iteration/。"},
    ]
    spec = {
        "title": f"算法迭代优化报告 · {tag}",
        "subtitle": "多指标引导目标 + 相对改进率终止 + 迭代追溯（方案 V3 落地）",
        "meta": "OR-Expert ｜ 阶段二：算法迭代优化",
        "stage": "阶段二：迭代优化报告",
        "sections": sections,
    }
    path = os.path.join(OUT, f"report_iteration_{tag}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, ensure_ascii=False, indent=2)
    return path


def main():
    tag = "medium"
    time_limit = 20.0
    r = run_experiment(tag=tag, time_limit=time_limit, seed=42)
    p1, p2, p3 = make_plots(r, tag)
    snaps, snap_path = make_snapshots(r, tag)
    report_json = build_report(r, tag, p1, p2, p3, snaps)
    print(f"\n=== 交付 ===")
    print(f"  收敛曲线: {p1}")
    print(f"  目标对比: {p2}")
    print(f"  质量对比: {p3}")
    print(f"  迭代快照: {snap_path}")
    print(f"  报告 JSON: {report_json}")


if __name__ == "__main__":
    main()
