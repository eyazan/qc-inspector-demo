"""Lightweight in-process metrics (no external dependency).

Counters + latency sums keyed by label. Rendered as JSON (/metrics) and in a
Prometheus-style text form for scrapers. Swap for prometheus_client later without
changing call sites (incr / observe)."""

import threading
import time
from collections import defaultdict
from contextlib import contextmanager

_lock = threading.Lock()
_counters: dict[str, float] = defaultdict(float)
_latency_sum: dict[str, float] = defaultdict(float)
_latency_count: dict[str, int] = defaultdict(int)


def incr(name: str, value: float = 1.0) -> None:
    with _lock:
        _counters[name] += value


def observe(name: str, seconds: float) -> None:
    with _lock:
        _latency_sum[name] += seconds
        _latency_count[name] += 1


@contextmanager
def timed(name: str):
    start = time.monotonic()
    try:
        yield
    finally:
        observe(name, time.monotonic() - start)


def snapshot() -> dict:
    with _lock:
        return {
            "counters": dict(_counters),
            "latency_avg_seconds": {
                k: round(_latency_sum[k] / _latency_count[k], 4)
                for k in _latency_sum
                if _latency_count[k]
            },
        }


def render_prometheus() -> str:
    snap = snapshot()
    lines = []
    for k, v in snap["counters"].items():
        metric = k.replace(".", "_").replace("-", "_")
        lines.append(f"qc_{metric} {v}")
    for k, v in snap["latency_avg_seconds"].items():
        metric = k.replace(".", "_").replace("-", "_")
        lines.append(f"qc_{metric}_avg_seconds {v}")
    return "\n".join(lines) + "\n"
