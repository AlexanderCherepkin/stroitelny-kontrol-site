#!/usr/bin/env python3
"""
Metrics Collector — lightweight in-memory metrics with Prometheus-compatible export.

Types:
  Counter   — monotonically increasing (requests, errors)
  Gauge     — can go up and down (queue depth, active sessions)
  Histogram — bucketed observations (latency_ms)

Export formats:
  JSON      — programmatic consumption
  Prometheus text — scraping by Prometheus/Grafana

Usage:
    from runtime.observability import MetricsCollector
    m = MetricsCollector()
    m.counter("pipeline.runs").inc()
    m.gauge("sessions.active").set(3)
    m.histogram("agent.latency_ms").observe(120.5)
    print(m.to_prometheus())
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any


class Counter:
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._value = 0.0

    def inc(self, amount: float = 1.0) -> None:
        self._value += amount

    @property
    def value(self) -> float:
        return self._value


class Gauge:
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._value = 0.0

    def set(self, value: float) -> None:
        self._value = value

    def inc(self, amount: float = 1.0) -> None:
        self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        self._value -= amount

    @property
    def value(self) -> float:
        return self._value


class Histogram:
    DEFAULT_BUCKETS = [5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]

    def __init__(self, name: str, description: str = "", buckets: list[float] | None = None):
        self.name = name
        self.description = description
        self.buckets = sorted(buckets or self.DEFAULT_BUCKETS)
        self._counts: dict[float, int] = {b: 0 for b in self.buckets}
        self._sum = 0.0
        self._count = 0

    def observe(self, value: float) -> None:
        self._sum += value
        self._count += 1
        for b in self.buckets:
            if value <= b:
                self._counts[b] += 1

    @property
    def sum(self) -> float:
        return self._sum

    @property
    def count(self) -> int:
        return self._count


@dataclass
class MetricsSnapshot:
    timestamp: float = field(default_factory=time.time)
    counters: dict[str, float] = field(default_factory=dict)
    gauges: dict[str, float] = field(default_factory=dict)
    histograms: dict[str, dict[str, Any]] = field(default_factory=dict)


class MetricsCollector:
    """Thread-safe (in asyncio single-thread sense) metrics registry."""

    def __init__(self):
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}

    def counter(self, name: str, description: str = "") -> Counter:
        if name not in self._counters:
            self._counters[name] = Counter(name, description)
        return self._counters[name]

    def gauge(self, name: str, description: str = "") -> Gauge:
        if name not in self._gauges:
            self._gauges[name] = Gauge(name, description)
        return self._gauges[name]

    def histogram(self, name: str, description: str = "", buckets: list[float] | None = None) -> Histogram:
        if name not in self._histograms:
            self._histograms[name] = Histogram(name, description, buckets)
        return self._histograms[name]

    def snapshot(self) -> MetricsSnapshot:
        return MetricsSnapshot(
            counters={n: c.value for n, c in self._counters.items()},
            gauges={n: g.value for n, g in self._gauges.items()},
            histograms={
                n: {
                    "count": h.count,
                    "sum": h.sum,
                    "buckets": {str(b): c for b, c in h._counts.items()},
                }
                for n, h in self._histograms.items()
            },
        )

    def to_json(self) -> str:
        snap = self.snapshot()
        return json.dumps({
            "timestamp": snap.timestamp,
            "counters": snap.counters,
            "gauges": snap.gauges,
            "histograms": snap.histograms,
        }, indent=2, default=str)

    def to_prometheus(self) -> str:
        lines: list[str] = []
        for n, c in self._counters.items():
            lines.append(f"# HELP {n} {c.description or n}")
            lines.append(f"# TYPE {n} counter")
            lines.append(f"{n} {c.value}")
        for n, g in self._gauges.items():
            lines.append(f"# HELP {n} {g.description or n}")
            lines.append(f"# TYPE {n} gauge")
            lines.append(f"{n} {g.value}")
        for n, h in self._histograms.items():
            lines.append(f"# HELP {n} {h.description or n}")
            lines.append(f"# TYPE {n} histogram")
            for b, c in h._counts.items():
                lines.append(f'{n}_bucket{{le="{b}"}} {c}')
            lines.append(f"{n}_sum {h.sum}")
            lines.append(f"{n}_count {h.count}")
        return "\n".join(lines) + "\n"
