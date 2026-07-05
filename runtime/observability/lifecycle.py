#!/usr/bin/env python3
"""
Graceful Shutdown — handles SIGTERM/SIGINT, drains in-flight work, closes resources.

Usage:
    from runtime.observability import GracefulShutdown
    gs = GracefulShutdown()
    gs.register_cleanup(bus.stop)
    gs.register_cleanup(worker_pool.stop)
    gs.register_cleanup(state_manager.close)
    gs.enable()
    # ... main loop ...
    await gs.wait_for_shutdown()
"""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import Any, Callable, Coroutine


class GracefulShutdown:
    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self._shutdown_event = asyncio.Event()
        self._cleanups: list[Callable[..., Any]] = []
        self._enabled = False
        self._exit_code = 0

    def register_cleanup(self, fn: Callable[..., Any]) -> None:
        """Register an async or sync cleanup callable."""
        self._cleanups.append(fn)

    def enable(self) -> None:
        """Install signal handlers. Call once in main thread."""
        if self._enabled:
            return
        self._enabled = True
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self._signal_handler)
        except RuntimeError:
            pass

    def _signal_handler(self) -> None:
        self._shutdown_event.set()

    async def wait_for_shutdown(self) -> int:
        """Block until shutdown signal received, then run cleanups. Returns exit code."""
        await self._shutdown_event.wait()
        return await self._run_cleanups()

    async def _run_cleanups(self) -> int:
        """Execute all registered cleanup functions with timeout."""
        import time
        deadline = time.monotonic() + self.timeout
        for fn in self._cleanups:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                if asyncio.iscoroutinefunction(fn):
                    await asyncio.wait_for(fn(), timeout=remaining)
                else:
                    fn()
            except Exception as e:
                self._exit_code = 1
                print(f"[shutdown] Cleanup error: {e}", file=sys.stderr)
        return self._exit_code

    def trigger(self) -> None:
        """Programmatically trigger shutdown (for testing)."""
        self._shutdown_event.set()
