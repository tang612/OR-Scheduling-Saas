#!/usr/bin/env python3
"""通用数学模型渲染器：将模型公式渲染为高可读性 PNG 图片。

不依赖任何 Markdown/LaTeX 渲染器 —— 输出为图片，任何环境（聊天/文档/邮件）直接可见。

用法:
    python3 scripts/render_model.py 输入.json 输出.png

输入 JSON 结构:
{
  "title": "模型标题",
  "subtitle": "副标题/问题类型",
  "sections": [
    {"heading": "集合", "lines": ["公式行1(支持 $...$ 数学+外部中文)", "公式行2"]},
    ...
  ],
  "footer": "底部说明(可选)"
}

依赖: matplotlib（mathtext 数学排版，数学符号接近 LaTeX）
"""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

# ---- 中文字体注册（macOS 系统字体，按可用性 fallback）----
_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
]
for f in _CANDIDATES:
    try:
        fm.fontManager.addfont(f)
    except Exception:
        pass
plt.rcParams["font.family"] = ["STHeiti", "Hiragino Sans GB", "Heiti SC", "sans-serif"]
plt.rcParams["mathtext.fontset"] = "stix"
plt.rcParams["axes.unicode_minus"] = False


def render(spec: dict, out_path: str, dpi: int = 200) -> None:
    title = spec.get("title", "数学模型")
    subtitle = spec.get("subtitle", "")
    footer = spec.get("footer", "")

    # 估算画布高度: 标题 + 副标题 + 每 heading + 每 line
    n_lines = 3 + sum(1 + len(sec.get("lines", [])) for sec in spec.get("sections", [])) + (1 if footer else 0)
    fig_h = max(6.0, n_lines * 0.62 + 1.2)
    fig = plt.figure(figsize=(13.5, fig_h), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")

    y = 0.985
    step = 0.62 / fig_h  # 每行高度自适应

    def line(txt, size=15, weight="normal", color="#1a1a2e", dy=None, align="left"):
        nonlocal y
        ax.text(0.03 if align == "left" else 0.5, y, txt, fontsize=size, fontweight=weight,
                color=color, va="top", ha=align, linespacing=1.9)
        y -= (dy if dy else step)

    line(title, size=22, weight="bold", color="#4a6cf7", dy=step * 1.35)
    if subtitle:
        line(subtitle, size=13, color="#666", dy=step * 1.05)

    for sec in spec.get("sections", []):
        line(sec.get("heading", ""), size=16, weight="bold", color="#4a6cf7", dy=step * 1.05)
        for ln in sec.get("lines", []):
            line(ln, size=15)

    if footer:
        line(footer, size=12, color="#888", dy=step * 1.2)

    fig.savefig(out_path, dpi=dpi, facecolor="white", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("用法: python3 render_model.py 输入.json 输出.png")
    with open(sys.argv[1], encoding="utf-8") as f:
        spec = json.load(f)
    render(spec, sys.argv[2])
    print(f"PNG 已生成: {sys.argv[2]}")
