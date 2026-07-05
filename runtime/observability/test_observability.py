#!/usr/bin/env python3
"""
Tests for observability components: logger, metrics, lifecycle, health.
"""

from __future__ import annotations

import asyncio
import json
import logging
import logging.handlers
import os
import signal
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

from runtime.observability.logger import (
    StructuredLogger,
    _JSONFormatter,
    get_logger,
    configure_log_level,
    add_file_handler,
)
from runtime.observability.metrics import Counter, Gauge, Histogram, MetricsCollector
from runtime.observability.lifecycle import GracefulShutdown
from runtime.observability.health import HealthCheck, HealthStatus


# ───────────────────────── Logger tests ─────────────────────────

class TestJSONFormatter:
    def test_basic_fields(self):
        formatter = _JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Hello",
            args=(),
            exc_info=None,
        )
        record.created = time.time()
        record.msecs = 123
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Hello"
        assert parsed["logger"] == "test.logger"
        assert "timestamp" in parsed

    def test_extra_fields(self):
        formatter = _JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Fail",
            args=(),
            exc_info=None,
        )
        record.created = time.time()
        record.msecs = 0
        record.session_id = "abc123"
        record.agent_path = "safety/input.md"
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["session_id"] == "abc123"
        assert parsed["agent_path"] == "safety/input.md"


class TestStructuredLogger:
    def test_log_levels(self, capsys):
        configure_log_level("DEBUG")
        log = get_logger("test_structured")
        log.info("info_msg", session_id="s1")
        log.error("err_msg", error="boom")
        captured = capsys.readouterr()
        lines = [l for l in captured.out.splitlines() if l.strip()]
        assert any("info_msg" in l and '"level": "INFO"' in l for l in lines)
        assert any("err_msg" in l and '"level": "ERROR"' in l for l in lines)

    def test_file_handler(self, tmp_path):
        log_file = tmp_path / "test.log"
        # Isolate logger state for this test
        test_logger = logging.getLogger("test_file_logger")
        test_logger.setLevel(logging.INFO)
        fh = logging.handlers.RotatingFileHandler(log_file, maxBytes=10_000_000, backupCount=1, encoding="utf-8")
        fh.setFormatter(_JSONFormatter())
        test_logger.handlers = [fh]
        log = StructuredLogger("test_file_logger")
        log.info("to_file", key="val")
        fh.flush()
        content = log_file.read_text()
        assert "to_file" in content
        assert "val" in content


# ───────────────────────── Metrics tests ─────────────────────────

class TestCounter:
    def test_inc(self):
        c = Counter("requests")
        c.inc()
        c.inc(2.5)
        assert c.value == 3.5


class TestGauge:
    def test_set_inc_dec(self):
        g = Gauge("active")
        g.set(5)
        g.inc()
        g.dec(2)
        assert g.value == 4


class TestHistogram:
    def test_observe_buckets(self):
        h = Histogram("latency", buckets=[10, 50, 100])
        h.observe(5)
        h.observe(25)
        h.observe(75)
        assert h.count == 3
        assert h.sum == 105
        assert h._counts[10] == 1
        assert h._counts[50] == 2
        assert h._counts[100] == 3


class TestMetricsCollector:
    def test_counter_gauge_histogram(self):
        m = MetricsCollector()
        m.counter("c1").inc(2)
        m.gauge("g1").set(7)
        m.histogram("h1").observe(42)
        snap = m.snapshot()
        assert snap.counters["c1"] == 2
        assert snap.gauges["g1"] == 7
        assert snap.histograms["h1"]["count"] == 1
        assert snap.histograms["h1"]["sum"] == 42

    def test_to_json(self):
        m = MetricsCollector()
        m.counter("c").inc()
        j = json.loads(m.to_json())
        assert j["counters"]["c"] == 1
        assert "timestamp" in j

    def test_to_prometheus(self):
        m = MetricsCollector()
        m.counter("c").inc()
        m.gauge("g").set(3)
        m.histogram("h").observe(20)
        text = m.to_prometheus()
        assert "c 1" in text
        assert "g 3" in text
        assert 'h_bucket{le="25"} 1' in text
        assert "h_sum 20" in text
        assert "h_count 1" in text


# ───────────────────────── Lifecycle tests ─────────────────────────

class TestGracefulShutdown:
    def test_register_and_trigger(self):
        gs = GracefulShutdown(timeout=1.0)
        cleaned = []
        gs.register_cleanup(lambda: cleaned.append("sync"))
        gs.trigger()
        asyncio.run(gs.wait_for_shutdown())
        assert cleaned == ["sync"]
        assert gs._exit_code == 0

    def test_async_cleanup(self):
        gs = GracefulShutdown(timeout=1.0)
        cleaned = []
        async def async_clean():
            cleaned.append("async")
        gs.register_cleanup(async_clean)
        gs.trigger()
        asyncio.run(gs.wait_for_shutdown())
        assert cleaned == ["async"]

    def test_timeout(self):
        gs = GracefulShutdown(timeout=0.01)
        async def slow():
            await asyncio.sleep(10)
        gs.register_cleanup(slow)
        gs.trigger()
        code = asyncio.run(gs.wait_for_shutdown())
        assert code == 1  # exit code set on exception/timeout


# ───────────────────────── Health tests ─────────────────────────

class TestHealthCheck:
    def test_all_healthy(self):
        h = HealthCheck()
        h.mark_component("a", True)
        h.mark_component("b", True)
        s = h.status()
        assert s.status == "healthy"
        assert s.components == {"a": True, "b": True}

    def test_degraded(self):
        h = HealthCheck()
        h.mark_component("a", True)
        h.mark_component("b", False)
        s = h.status()
        assert s.status == "degraded"

    def test_unhealthy(self):
        h = HealthCheck()
        h.mark_component("a", False)
        h.mark_component("b", False)
        s = h.status()
        assert s.status == "unhealthy"

    def test_empty_is_healthy(self):
        h = HealthCheck()
        s = h.status()
        assert s.status == "healthy"

    def test_to_json(self):
        h = HealthCheck()
        h.mark_component("x", True)
        j = json.loads(h.to_json())
        assert j["status"] == "healthy"
        assert j["components"]["x"] is True
        assert "timestamp" in j


# ───────────────────────── Integration ─────────────────────────

class TestObservabilityIntegration:
    def test_full_pipeline(self, tmp_path):
        """Logger + metrics + health work together end-to-end."""
        log_file = tmp_path / "integration.log"
        add_file_handler(log_file)
        log = get_logger("integration")

        metrics = MetricsCollector()
        health = HealthCheck()

        log.info("start", session_id="s1")
        metrics.counter("runs").inc()
        health.mark_component("pipeline", True)

        assert json.loads(health.to_json())["status"] == "healthy"
        assert metrics.snapshot().counters["runs"] == 1
        logging.getLogger().handlers[-1].flush()
        assert "start" in log_file.read_text()
