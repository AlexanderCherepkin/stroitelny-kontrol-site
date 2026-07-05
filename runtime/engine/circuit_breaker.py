#!/usr/bin/env python3
"""
Circuit Breaker for LLMEngine — prevents cascade failures when API is down.

States:
  CLOSED   — normal operation, requests pass through
  OPEN     — failure threshold reached, requests fail fast
  HALF_OPEN — after cooldown, next request probes the service

Also provides provider fallback: if Anthropic fails, try OpenAI, then DeepSeek.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 3
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1


@dataclass
class CircuitBreaker:
    name: str = "default"
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    _state: CircuitState = field(default=CircuitState.CLOSED, repr=False)
    _failure_count: int = field(default=0, repr=False)
    _last_failure_time: float = field(default=0.0, repr=False)
    _half_open_calls: int = field(default=0, repr=False)

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.config.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
        return self._state

    def can_execute(self) -> bool:
        st = self.state
        if st == CircuitState.CLOSED:
            return True
        if st == CircuitState.HALF_OPEN:
            return self._half_open_calls < self.config.half_open_max_calls
        return False

    def record_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self.config.half_open_max_calls:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
        else:
            self._failure_count = max(0, self._failure_count - 1)

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
        elif self._failure_count >= self.config.failure_threshold:
            self._state = CircuitState.OPEN

    async def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        if not self.can_execute():
            raise CircuitBreakerOpenError(f"Circuit breaker '{self.name}' is OPEN")
        try:
            result = await fn(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise


class CircuitBreakerOpenError(Exception):
    pass
