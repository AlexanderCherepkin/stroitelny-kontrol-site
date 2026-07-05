"""pytest tests for the Mem0 MCP server.

These tests verify tool registration, degraded mode when mem0ai is not installed,
and the mapping from MCP tool calls to the runtime client.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.mem0_server import Mem0MCPServer


@pytest.fixture
def mem0_server() -> Mem0MCPServer:
    return Mem0MCPServer()


@pytest.fixture
def degraded_server(tmp_path: Path) -> Mem0MCPServer:
    server = Mem0MCPServer(str(tmp_path))
    server._degraded_reason = "mem0ai is not installed"
    return server


def test_mem0_server_initializes(mem0_server: Mem0MCPServer) -> None:
    assert mem0_server.name == "mem0"
    assert mem0_server._initialized is True
    tools = mem0_server.get_tools_list()
    assert len(tools) == 4
    names = {t["name"] for t in tools}
    expected = {"mem0_add", "mem0_search", "mem0_get_all", "mem0_delete"}
    assert names == expected


def test_mem0_server_degraded_without_package(degraded_server: Mem0MCPServer) -> None:
    result = degraded_server.mem0_search(query="test")
    assert result["status"] == "degraded"
    assert "mem0ai" in result["error"]


def test_mem0_server_ping(mem0_server: Mem0MCPServer) -> None:
    import asyncio

    assert asyncio.run(mem0_server.ping()) is True


def test_mem0_tool_schemas(mem0_server: Mem0MCPServer) -> None:
    for tool in mem0_server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def _simulate_client_available(server: Mem0MCPServer) -> None:
    server._degraded_reason = None
    server._client = MagicMock()


def test_mem0_add_invokes_client(mem0_server: Mem0MCPServer) -> None:
    _simulate_client_available(mem0_server)
    mem0_server._client.add.return_value = {"id": "mem-1", "status": "stored"}

    result = mem0_server.mem0_add(messages="important fact")
    assert result["id"] == "mem-1"
    mem0_server._client.add.assert_called_once()


def test_mem0_search_invokes_client(mem0_server: Mem0MCPServer) -> None:
    _simulate_client_available(mem0_server)
    mem0_server._client.search.return_value = {"results": [{"id": "mem-1"}], "total_found": 1}

    result = mem0_server.mem0_search(query="important")
    assert result["total_found"] == 1
    mem0_server._client.search.assert_called_once()


def test_mem0_get_all_invokes_client(mem0_server: Mem0MCPServer) -> None:
    _simulate_client_available(mem0_server)
    mem0_server._client.get_all.return_value = {"results": [{"id": "mem-1"}], "total_found": 1}

    result = mem0_server.mem0_get_all(limit=5)
    assert result["total_found"] == 1
    mem0_server._client.get_all.assert_called_once()


def test_mem0_delete_invokes_client(mem0_server: Mem0MCPServer) -> None:
    _simulate_client_available(mem0_server)
    mem0_server._client.delete.return_value = {"deleted": True}

    result = mem0_server.mem0_delete(memory_id="mem-1")
    assert result["deleted"] is True
    mem0_server._client.delete.assert_called_once()
