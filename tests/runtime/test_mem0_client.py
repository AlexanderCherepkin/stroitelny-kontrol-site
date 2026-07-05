"""pytest tests for the Mem0 runtime client.

These tests verify graceful degradation when the mem0ai package is not installed
or the Mem0 cloud API is unreachable, and basic fallback behavior of the
add/search/get_all/delete primitives.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.engine.mem0_client import Mem0Client, Mem0Config, Mem0Unavailable


def _reset_singleton() -> None:
    Mem0Client._instance = None


def test_mem0_client_singleton() -> None:
    _reset_singleton()
    client1 = Mem0Client(Mem0Config(enabled=False))
    client2 = Mem0Client(Mem0Config(enabled=False))
    assert client1 is client2


def test_mem0_disabled_returns_passthrough() -> None:
    _reset_singleton()
    client = Mem0Client(Mem0Config(enabled=False))
    result = client.add(messages="hello")
    assert result["available"] is False
    assert result["operation"] == "add"


def test_mem0_fallback_add_and_search() -> None:
    _reset_singleton()
    client = Mem0Client(Mem0Config(enabled=True))
    client._mem0 = Mem0Unavailable()

    store = client._fallback_store
    store.clear()

    client.add(messages="The project uses Mem0 for long-term memory.")
    client.add(messages="Another unrelated fact.")

    result = client.search(query="long-term memory")
    assert result["available"] is False
    assert result["operation"] == "search"
    assert result["total_found"] == 1
    assert "Mem0" in result["results"][0]["memory"]


def test_mem0_fallback_get_all() -> None:
    _reset_singleton()
    client = Mem0Client(Mem0Config(enabled=True))
    client._mem0 = Mem0Unavailable()
    client._fallback_store.clear()

    client.add(messages="entry one")
    client.add(messages="entry two")

    result = client.get_all(limit=10)
    assert result["available"] is False
    assert result["operation"] == "get_all"
    assert result["total_found"] == 2
    assert len(result["results"]) == 2


def test_mem0_fallback_delete_is_no_op() -> None:
    _reset_singleton()
    client = Mem0Client(Mem0Config(enabled=True))
    client._mem0 = Mem0Unavailable()

    result = client.delete(memory_id="fallback-0")
    assert result["available"] is False
    assert result["operation"] == "delete"
    assert result["deleted"] is False


def test_mem0_stats_reports_fallback() -> None:
    _reset_singleton()
    client = Mem0Client(Mem0Config(enabled=True))
    client._mem0 = Mem0Unavailable()
    client._fallback_store.clear()

    client.add(messages="entry one")
    client.add(messages="entry two")
    stats = client.stats()
    assert stats["available"] is False
    assert stats["enabled"] is True
    assert stats["fallback_entries"] == 2


def test_mem0_to_dict_reports_unavailable_when_disabled() -> None:
    _reset_singleton()
    client = Mem0Client(Mem0Config(enabled=False))
    d = client.to_dict()
    assert d["available"] is False
    assert d["enabled"] is False
