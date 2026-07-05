"""pytest tests for the Headroom runtime client.

These tests verify graceful degradation when headroom-ai is not installed and
basic passthrough behavior of the client API.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.engine.headroom_client import HeadroomClient, HeadroomConfig, HeadroomUnavailable


def test_headroom_client_singleton() -> None:
    client1 = HeadroomClient(HeadroomConfig(enabled=False))
    client2 = HeadroomClient(HeadroomConfig(enabled=False))
    assert client1 is client2


def test_headroom_client_passthrough_when_unavailable() -> None:
    client = HeadroomClient(HeadroomConfig(enabled=True))
    client._headroom = HeadroomUnavailable()

    result = client.compress_text("some large tool output")
    assert result["available"] is False
    assert result["compressed"] == "some large tool output"
    assert result["hash"] == ""


def test_headroom_retrieve_passthrough_when_unavailable() -> None:
    client = HeadroomClient(HeadroomConfig(enabled=True))
    client._headroom = HeadroomUnavailable()

    result = client.retrieve("hash-123")
    assert result["available"] is False
    assert result["found"] is False
    assert result["original_content"] is None


def test_headroom_stats_passthrough_when_unavailable() -> None:
    client = HeadroomClient(HeadroomConfig(enabled=True))
    client._headroom = HeadroomUnavailable()

    result = client.stats()
    assert result["available"] is False
    assert result["compressions"] == 0


def test_headroom_shared_context_none_when_unavailable() -> None:
    client = HeadroomClient(HeadroomConfig(enabled=True))
    client._headroom = HeadroomUnavailable()

    assert client.shared_context() is None


def test_headroom_disabled_returns_passthrough() -> None:
    client = HeadroomClient(HeadroomConfig(enabled=False))
    result = client.compress_text("text")
    assert result["available"] is False


def test_headroom_to_dict_reports_unavailable_when_disabled() -> None:
    client = HeadroomClient(HeadroomConfig(enabled=False))
    assert client.to_dict()["available"] is False
    assert client.to_dict()["enabled"] is False
