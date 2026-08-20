#!/usr/bin/env python3
"""过程报告构建器：JSON 内容定义 → HTML 报告（MathJax 渲染数学公式）。

- 公式以 LaTeX 源码内嵌于 HTML（可编辑、可版本化），浏览器打开即渲染
- 分阶段生成：阶段一（数学模型）供人工审核，确认后补充阶段二内容重新生成
- 用法: python3 scripts/build_report.py docs/report_<任务名>.json docs/<报告名>.html

JSON 结构:
{
  "title": str, "subtitle": str, "meta": str,
  "sections": [
    {"type": "heading", "level": 2, "text": "一、问题描述"},
    {"type": "text", "text": "段落文本（可含行内 $...$ 公式）"},
    {"type": "math", "tex": "LaTeX 源码", "tag": "(1)"},
    {"type": "code", "lang": "python", "code": "..."},
    {"type": "table", "headers": ["a","b"], "rows": [["1","2"]]},
    {"type": "note", "text": "提示/声明"}
  ]
}
"""
import html
import json
import sys
from datetime import datetime

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<script>
  MathJax = {{
    tex: {{
      tags: 'none',
      inlineMath: [['$', '$'], ['\\(', '\\)']],
      displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']]
    }}
  }};
</script>
<script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
<style>
  body {{ font-family: "PingFang SC", "Microsoft YaHei", sans-serif; max-width: 900px; margin: 0 auto; padding: 36px 28px; color: #1a1a2e; line-height: 1.8; }}
  h1 {{ font-size: 24px; border-bottom: 3px solid #4a6cf7; padding-bottom: 12px; }}
  h2 {{ font-size: 19px; color: #4a6cf7; margin-top: 34px; border-left: 4px solid #4a6cf7; padding-left: 10px; }}
  h3 {{ font-size: 16px; margin-top: 24px; color: #333; }}
  .subtitle {{ color: #666; font-size: 14px; margin-top: -8px; }}
  .meta {{ color: #888; font-size: 12px; margin-top: 6px; }}
  .stage-badge {{ display: inline-block; background: #4a6cf7; color: #fff; border-radius: 4px; padding: 2px 10px; font-size: 12px; margin-top: 12px; }}
  .stage-badge.pending {{ background: #e67e22; }}
  .eq {{ margin: 18px 0; text-align: left; }}
  table {{ border-collapse: collapse; margin: 14px 0; }}
  td, th {{ border: 1px solid #999; padding: 6px 18px; text-align: center; }}
  th {{ background: #f0f4ff; }}
  pre {{ background: #f6f8fa; border: 1px solid #ddd; border-radius: 6px; padding: 14px; overflow-x: auto; font-size: 13px; line-height: 1.5; }}
  .note {{ background: #fff8e6; border: 1px solid #f0d78a; border-radius: 6px; padding: 10px 14px; margin: 12px 0; font-size: 14px; }}
  footer {{ margin-top: 44px; color: #aaa; font-size: 12px; border-top: 1px solid #eee; padding-top: 10px; }}
  mjx-container {{ font-size: 1.08em; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="subtitle">{subtitle}</div>
<div class="meta">{meta} ｜ 生成时间: {now}</div>
<div class="stage-badge {stage_class}">{stage}</div>
{sections}
<footer>OR-Expert 过程报告 ｜ 公式为 LaTeX 源码内嵌，可直接编辑后刷新浏览器重新渲染</footer>
</body>
</html>
"""


def render_section(sec: dict) -> str:
    t = sec.get("type", "text")
    if t == "heading":
        lvl = sec.get("level", 2)
        return f"<h{lvl}>{html.escape(sec['text'])}</h{lvl}>"
    if t == "text":
        return f"<p>{sec['text']}</p>"
    if t == "math":
        tag = f"\\tag{{{sec['tag']}}}" if sec.get("tag") else ""
        return f'<div class="eq">$$ {sec["tex"]} {tag} $$</div>'
    if t == "code":
        return (f'<pre><code class="language-{sec.get("lang", "")}">'
                f"{html.escape(sec['code'])}</code></pre>")
    if t == "table":
        headers = "".join(f"<th>{html.escape(h)}</th>" for h in sec["headers"])
        rows = "".join(
            "<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in row) + "</tr>"
            for row in sec["rows"]
        )
        return f"<table><tr>{headers}</tr>{rows}</table>"
    if t == "mapping":
        # 反幻觉核对清单：公式-代码逐行对照表，mismatch=True 的行整行标红
        headers = "".join(f"<th>{html.escape(h)}</th>" for h in sec["headers"])
        rows_html = ""
        for row in sec["rows"]:
            cls = ' style="background:#fdecea; color:#c0392b; font-weight:bold;"' if row.get("mismatch") else ""
            cells = "".join(f"<td>{html.escape(str(c))}</td>" for c in row["cells"])
            rows_html += f"<tr{cls}>{cells}</tr>"
        return (f'<table style="border-collapse:collapse; margin:14px 0;">'
                f"<tr>{headers}</tr>{rows_html}</table>")
    if t == "figure":
        cap = f'<figcaption style="color:#666; font-size:13px; margin-top:6px;">{sec["caption"]}</figcaption>' if sec.get("caption") else ""
        return (f'<figure style="text-align:center; margin:18px 0;">'
                f'<img src="{sec["src"]}" style="max-width:100%; border:1px solid #eee; border-radius:6px;">{cap}</figure>')
    if t == "code_file":
        with open(sec["path"], encoding="utf-8") as fh:
            code = fh.read()
        return (f'<pre><code class="language-{sec.get("lang", "")}">'
                f"{html.escape(code)}</code></pre>")
    if t == "note":
        return f'<div class="note">⚠ {sec["text"]}</div>'
    return ""


def build(spec: dict) -> str:
    stage = spec.get("stage", "阶段一：数学模型（待人工审核）")
    pending = "pending" if "审核" in stage else "ok"
    sections = "\n".join(render_section(s) for s in spec.get("sections", []))
    return HTML_TEMPLATE.format(
        title=html.escape(spec.get("title", "过程报告")),
        subtitle=html.escape(spec.get("subtitle", "")),
        meta=html.escape(spec.get("meta", "")),
        now=datetime.now().strftime("%Y-%m-%d %H:%M"),
        stage=html.escape(stage),
        stage_class=pending,
        sections=sections,
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("用法: python3 build_report.py 内容.json 输出.html")
    with open(sys.argv[1], encoding="utf-8") as f:
        spec = json.load(f)
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        f.write(build(spec))
    print(f"报告已生成: {sys.argv[2]}")
