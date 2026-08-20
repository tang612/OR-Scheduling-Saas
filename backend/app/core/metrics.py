"""轻量 Prometheus 指标：计数器 + 直方图，输出 text/plain 格式。

自研实现（无第三方依赖），覆盖 HTTP 指标 + 业务指标：
- http_requests_total{method,path,status}
- http_request_duration_seconds（简化分桶）
- 业务计数器（tasks/solutions/datasets 等）
"""
import time
from collections import defaultdict
from threading import Lock

_lock = Lock()
_counters: dict[tuple, int] = defaultdict(int)
_histograms: dict[tuple, dict] = defaultdict(
    lambda: {"sum": 0.0, "count": 0, "buckets": defaultdict(int)}
)

_HIST_BUCKETS = (0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0)


def inc_counter(name: str, labels: tuple[tuple[str, str], ...] = ()) -> None:
    with _lock:
        _counters[(name, labels)] += 1


def observe_histogram(name: str, value: float, labels: tuple[tuple[str, str], ...] = ()) -> None:
    with _lock:
        h = _histograms[(name, labels)]
        h["sum"] += value
        h["count"] += 1
        for b in _HIST_BUCKETS:
            if value <= b:
                h["buckets"][b] += 1


def _fmt_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    return "{" + ",".join(f'{k}="{v}"' for k, v in labels) + "}"


def render() -> str:
    """渲染 Prometheus text/plain 格式。"""
    lines: list[str] = []
    with _lock:
        for (name, labels), val in sorted(_counters.items()):
            lines.append(f"{name}{_fmt_labels(labels)} {val}")
        for (name, labels), h in sorted(_histograms.items()):
            base = f"{name}{_fmt_labels(labels)}"
            lines.append(f"{base}_sum {h['sum']}")
            lines.append(f"{base}_count {h['count']}")
            for b in _HIST_BUCKETS:
                lines.append(f"{base}_bucket{{le=\"{b}\"}} {h['buckets'][b]}")
            lines.append(f"{base}_bucket{{le=\"+Inf\"}} {h['count']}")
    return "\n".join(lines) + "\n"
