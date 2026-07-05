#!/usr/bin/env python3
"""Unit tests for resilience improvements: circuit breaker, health checks, backpressure, priorities, metrics."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime.engine.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState, CircuitBreakerOpenError
from runtime.workers.worker_pool import WorkerPool, WorkerJob, WorkerResult
from mcp_servers.base import MCPServer
from mcp_servers.registry import MCPRegistry, ServerInfo


class TestCircuitBreaker(unittest.TestCase):
    def test_starts_closed(self):
        cb = CircuitBreaker()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.can_execute())

    def test_opens_after_failures(self):
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=2))
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.can_execute())

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01))
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)
        import time
        time.sleep(0.02)
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)
        self.assertTrue(cb.can_execute())

    def test_success_resets(self):
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=2))
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_call_wrapper(self):
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=2))

        async def good():
            return "ok"

        async def bad():
            raise RuntimeError("fail")

        async def _run():
            self.assertEqual(await cb.call(good), "ok")
            with self.assertRaises(RuntimeError):
                await cb.call(bad)
            with self.assertRaises(RuntimeError):
                await cb.call(bad)
            with self.assertRaises(CircuitBreakerOpenError):
                await cb.call(good)

        asyncio.run(_run())

    def test_async_wrapper(self):
        self.test_call_wrapper()


class TestWorkerPoolBackpressure(unittest.TestCase):
    def setUp(self):
        # Zero workers so nothing drains the queue — backpressure triggers immediately
        self.pool = WorkerPool(max_workers=0, max_queue_size=2)

    def tearDown(self):
        asyncio.run(self.pool.stop())

    def test_rejects_when_queue_full(self):
        async def _test():
            await self.pool.start()
            j1 = WorkerJob(priority=5)
            j2 = WorkerJob(priority=5)
            j3 = WorkerJob(priority=5)
            r1 = await self.pool.dispatch(j1)
            r2 = await self.pool.dispatch(j2)
            r3 = await self.pool.dispatch(j3)
            statuses = [r1.status, r2.status, r3.status]
            self.assertIn("rejected", statuses)
            self.assertGreaterEqual(self.pool.rejected_jobs, 1)

        asyncio.run(_test())


class TestWorkerJobPriority(unittest.TestCase):
    def test_priority_sorting(self):
        jobs = [
            WorkerJob(priority=5),
            WorkerJob(priority=1),
            WorkerJob(priority=3),
        ]
        jobs.sort()
        self.assertEqual([j.priority for j in jobs], [1, 3, 5])


class TestMCPHealthCheck(unittest.TestCase):
    def test_server_ping(self):
        server = MCPServer(name="test-server")
        self.assertFalse(asyncio.run(server.ping()))
        server._initialized = True
        self.assertTrue(asyncio.run(server.ping()))

    def test_registry_is_healthy(self):
        registry = MCPRegistry()
        server = MCPServer(name="test")
        server._initialized = True
        server.register("echo", "Echo tool", {"type": "object"}, lambda x: x)
        registry.register(ServerInfo(name="test", category="tools_read", agent_count=1, server=server, tools=["echo"]))
        self.assertTrue(registry.is_healthy("echo"))
        self.assertFalse(registry.is_healthy("missing"))


if __name__ == "__main__":
    unittest.main()
