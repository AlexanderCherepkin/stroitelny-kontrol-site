"""pytest tests for the Headroom MCP server.

These tests verify tool registration, degraded mode when headroom-ai is not
installed, and the mapping from MCP tool calls to the runtime client.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.headroom_server import HeadroomMCPServer


@pytest.fixture
def headroom_server() -> HeadroomMCPServer:
    return HeadroomMCPServer()


@pytest.fixture
def degraded_server(tmp_path: Path) -> HeadroomMCPServer:
    """Server created in a workspace that does not affect availability; we force
    degraded mode by patching _ensure_headroom in the test."""
    server = HeadroomMCPServer(str(tmp_path))
    return server


def test_headroom_server_initializes(headroom_server: HeadroomMCPServer) -> None:
    assert headroom_server.name == "headroom"
    assert headroom_server._initialized is True
    tools = headroom_server.get_tools_list()
    assert len(tools) == 3
    names = {t["name"] for t in tools}
    expected = {"headroom_compress", "headroom_retrieve", "headroom_stats"}
    assert names == expected


def test_headroom_server_degraded_without_package(degraded_server: HeadroomMCPServer) -> None:
    degraded_server._headroom = None
    degraded_server._degraded_reason = "headroom-ai is not installed"
    result = degraded_server.headroom_compress(content="test")
    assert result["status"] == "degraded"
    assert "headroom-ai" in result["error"]


def test_headroom_server_ping(headroom_server: HeadroomMCPServer) -> None:
    import asyncio

    assert asyncio.run(headroom_server.ping()) is True


def test_headroom_tool_schemas(headroom_server: HeadroomMCPServer) -> None:
    for tool in headroom_server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def _simulate_sdk_available(server: HeadroomMCPServer) -> None:
    """Clear degraded state and install a minimal mock headroom module."""
    server._degraded_reason = None
    server._headroom = MagicMock()


def test_headroom_compress_invokes_sdk(headroom_server: HeadroomMCPServer) -> None:
    _simulate_sdk_available(headroom_server)

    mock_result = MagicMock()
    mock_result.tokens_before = 1000
    mock_result.tokens_after = 300
    mock_result.messages = [{"role": "tool", "content": "compressed"}]
    mock_result.transforms_applied = ["summary"]
    headroom_server._headroom.compress.return_value = mock_result

    mock_store = MagicMock()
    mock_store.store.return_value = "hash-123"

    with patch.object(headroom_server, "_get_store", return_value=mock_store):
        result = headroom_server.headroom_compress(content="large content", target_ratio=0.3)

    assert result["status"] == "success"
    assert result["hash"] == "hash-123"
    assert result["original_tokens"] == 1000
    assert result["compressed_tokens"] == 300
    assert result["tokens_saved"] == 700
    assert result["savings_percent"] == 70.0


def test_headroom_retrieve_by_hash(headroom_server: HeadroomMCPServer) -> None:
    _simulate_sdk_available(headroom_server)

    mock_entry = MagicMock()
    mock_entry.original_content = "original content"

    mock_store = MagicMock()
    mock_store.retrieve.return_value = mock_entry

    with patch.object(headroom_server, "_get_store", return_value=mock_store):
        result = headroom_server.headroom_retrieve(hash="hash-123")

    assert result["status"] == "success"
    assert result["found"] is True
    assert result["original_content"] == "original content"


def test_headroom_retrieve_not_found(headroom_server: HeadroomMCPServer) -> None:
    _simulate_sdk_available(headroom_server)

    mock_store = MagicMock()
    mock_store.retrieve.return_value = None

    with patch.object(headroom_server, "_get_store", return_value=mock_store):
        result = headroom_server.headroom_retrieve(hash="missing")

    assert result["status"] == "not_found"
    assert result["found"] is False
