#!/usr/bin/env python3
"""
Health Check — runtime health status for load balancers and monitoring.

States:
  HEALTHY   — all components operational
  DEGRADED  — some optional component down (e.g. memory, worker pool)
  UNHEALTHY — critical component down (LLM engine, state DB)

Usage:
    from runtime.observability import HealthCheck
    h = HealthCheck()
    h.mark_component("llm", True)
    h.mark_component("state_db", False)
    print(h.status())  # unhealthy
    print(h.to_json())
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HealthStatus:
    status: str  # healthy | degraded | unhealthy
    components: dict[str, bool]
    timestamp: float = field(default_factory=time.time)


class HealthCheck:
    def __init__(self):
        self._components: dict[str, bool] = {}

    def mark_component(self, name: str, healthy: bool) -> None:
        self._components[name] = healthy

    def status(self) -> HealthStatus:
        values = list(self._components.values())
        if not values:
            return HealthStatus("healthy", {})
        if all(values):
            return HealthStatus("healthy", dict(self._components))
        if any(values):
            return HealthStatus("degraded", dict(self._components))
        return HealthStatus("unhealthy", dict(self._components))

    def to_json(self) -> str:
        s = self.status()
        return json.dumps({
            "status": s.status,
            "components": s.components,
            "timestamp": s.timestamp,
        }, default=str)
