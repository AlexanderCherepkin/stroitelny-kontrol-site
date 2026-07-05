"""pytest tests for the Backend MCP server.

These tests mock subprocess invocation so they run without a real backend spec
and verify tool registration, schema shape, and the mapping from MCP tool calls
to figma-agent-core/backend_bridge.py.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.backend_server import BackendMCPServer


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def backend_server(project_root: Path) -> BackendMCPServer:
    return BackendMCPServer(str(project_root))


@pytest.fixture
def degraded_server(tmp_path: Path) -> BackendMCPServer:
    empty_workspace = tmp_path / "no_backend_core"
    empty_workspace.mkdir()
    return BackendMCPServer(str(empty_workspace))


def test_backend_server_initializes(backend_server: BackendMCPServer) -> None:
    assert backend_server.name == "backend"
    assert backend_server._initialized is True
    tools = backend_server.get_tools_list()
    assert len(tools) == 7
    names = {t["name"] for t in tools}
    expected = {
        "backend_analyze_spec",
        "backend_map_ui",
        "backend_generate_routes",
        "backend_generate_actions",
        "backend_sync_schema",
        "backend_run_bridge",
        "backend_generate_schemas",
    }
    assert names == expected


def test_backend_server_degraded_without_core(degraded_server: BackendMCPServer) -> None:
    assert degraded_server._degraded_reason is not None
    result = degraded_server.backend_analyze_spec()
    assert result["status"] == "degraded"
    assert "figma-agent-core not found" in result["error"]


def test_backend_server_ping(backend_server: BackendMCPServer) -> None:
    assert asyncio.run(backend_server.ping()) is True


def test_backend_tool_schemas(backend_server: BackendMCPServer) -> None:
    for tool in backend_server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_backend_analyze_spec_invokes_bridge(backend_server: BackendMCPServer) -> None:
    mock_result = MagicMock(returncode=0, stdout="{}", stderr="")
    with patch.object(subprocess, "run", return_value=mock_result):
        result = backend_server.backend_analyze_spec(openapi="spec.yaml")
    assert result["status"] == "success"
    assert result["stdout"] == "{}"


def test_backend_run_bridge_invokes_bridge_with_layout_ast(backend_server: BackendMCPServer) -> None:
    mock_result = MagicMock(returncode=0, stdout="OK", stderr="")
    with patch.object(subprocess, "run", return_value=mock_result):
        result = backend_server.backend_run_bridge(
            layout_ast="{}",
            text_spec="spec.json",
            output_dir="out",
            mapping_file="map.json",
        )
    assert result["status"] == "success"
