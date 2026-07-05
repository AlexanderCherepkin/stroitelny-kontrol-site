"""pytest tests for the Memanto MCP server.

These tests verify tool registration, degraded mode when the Memanto server is
not reachable, and the mapping from MCP tool calls to the runtime client.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.memanto_server import MemantoMCPServer


@pytest.fixture
def memanto_server() -> MemantoMCPServer:
    return MemantoMCPServer()


@pytest.fixture
def degraded_server(tmp_path: Path) -> MemantoMCPServer:
    server = MemantoMCPServer(str(tmp_path))
    server._degraded_reason = "Memanto server is not reachable"
    return server


def test_memanto_server_initializes(memanto_server: MemantoMCPServer) -> None:
    assert memanto_server.name == "memanto"
    assert memanto_server._initialized is True
    tools = memanto_server.get_tools_list()
    assert len(tools) == 4
    names = {t["name"] for t in tools}
    expected = {"memanto_create_agent", "memanto_remember", "memanto_recall", "memanto_answer"}
    assert names == expected


def test_memanto_server_degraded_without_server(degraded_server: MemantoMCPServer) -> None:
    result = degraded_server.memanto_remember(content="test")
    assert result["status"] == "degraded"
    assert "Memanto server" in result["error"]


def test_memanto_server_ping(memanto_server: MemantoMCPServer) -> None:
    import asyncio

    assert asyncio.run(memanto_server.ping()) is True


def test_memanto_tool_schemas(memanto_server: MemantoMCPServer) -> None:
    for tool in memanto_server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def _simulate_client_available(server: MemantoMCPServer) -> None:
    server._degraded_reason = None
    server._client = MagicMock()


def test_memanto_remember_invokes_client(memanto_server: MemantoMCPServer) -> None:
    _simulate_client_available(memanto_server)
    memanto_server._client.remember.return_value = {"id": "mem-1", "status": "stored"}

    result = memanto_server.memanto_remember(content="important fact", title="fact")
    assert result["id"] == "mem-1"
    memanto_server._client.remember.assert_called_once()


def test_memanto_recall_invokes_client(memanto_server: MemantoMCPServer) -> None:
    _simulate_client_available(memanto_server)
    memanto_server._client.recall.return_value = {"results": [{"id": "mem-1"}], "total_found": 1}

    result = memanto_server.memanto_recall(query="important")
    assert result["total_found"] == 1
    memanto_server._client.recall.assert_called_once()


def test_memanto_answer_invokes_client(memanto_server: MemantoMCPServer) -> None:
    _simulate_client_available(memanto_server)
    memanto_server._client.answer.return_value = {"answer": "We know X."}

    result = memanto_server.memanto_answer(query="What do we know?")
    assert result["answer"] == "We know X."
    memanto_server._client.answer.assert_called_once()


def test_memanto_create_agent_invokes_client(memanto_server: MemantoMCPServer) -> None:
    _simulate_client_available(memanto_server)
    memanto_server._client.create_agent.return_value = {"agent_id": "loop", "created": True}

    result = memanto_server.memanto_create_agent(agent_id="loop")
    assert result["agent_id"] == "loop"
    memanto_server._client.create_agent.assert_called_once()
