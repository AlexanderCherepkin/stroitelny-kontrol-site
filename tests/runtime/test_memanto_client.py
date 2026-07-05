"""pytest tests for the Memanto runtime client.

These tests verify graceful degradation when the Memanto server is not running
and basic fallback behavior of the remember/recall/answer primitives.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.engine.memanto_client import MemantoClient, MemantoConfig, MemantoUnavailable


def _reset_singleton() -> None:
    MemantoClient._instance = None


def test_memanto_client_singleton() -> None:
    _reset_singleton()
    client1 = MemantoClient(MemantoConfig(enabled=False))
    client2 = MemantoClient(MemantoConfig(enabled=False))
    assert client1 is client2


def test_memanto_disabled_returns_passthrough() -> None:
    _reset_singleton()
    client = MemantoClient(MemantoConfig(enabled=False))
    result = client.remember(content="fact", title="t")
    assert result["available"] is False
    assert result["operation"] == "remember"


def test_memanto_fallback_remember_and_recall() -> None:
    _reset_singleton()
    client = MemantoClient(MemantoConfig(enabled=True))
    client._sdk = MemantoUnavailable()

    store = client._fallback_store
    store.clear()

    client.remember(content="The project uses Memanto for long-term memory.", title="memanto usage")
    client.remember(content="Another unrelated fact.", title="other")

    result = client.recall(query="long-term memory")
    assert result["available"] is False
    assert result["operation"] == "recall"
    assert result["total_found"] == 1
    assert "Memanto" in result["results"][0]["content"]


def test_memanto_fallback_answer_empty() -> None:
    _reset_singleton()
    client = MemantoClient(MemantoConfig(enabled=True))
    client._sdk = MemantoUnavailable()

    result = client.answer(query="What do we know?")
    assert result["available"] is False
    assert result["operation"] == "answer"
    assert result["answer"] == ""


def test_memanto_create_agent_passthrough_when_unavailable() -> None:
    _reset_singleton()
    client = MemantoClient(MemantoConfig(enabled=True))
    client._sdk = MemantoUnavailable()

    result = client.create_agent(agent_id="test_agent")
    assert result["available"] is False
    assert result["operation"] == "create_agent"


def test_memanto_stats_reports_fallback() -> None:
    _reset_singleton()
    client = MemantoClient(MemantoConfig(enabled=True))
    client._sdk = MemantoUnavailable()
    client._fallback_store.clear()

    client.remember(content="entry one")
    client.remember(content="entry two")
    stats = client.stats()
    assert stats["available"] is False
    assert stats["fallback_entries"] == 2


def test_memanto_to_dict_reports_unavailable_when_disabled() -> None:
    _reset_singleton()
    client = MemantoClient(MemantoConfig(enabled=False))
    d = client.to_dict()
    assert d["available"] is False
    assert d["enabled"] is False
