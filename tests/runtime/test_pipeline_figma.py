"""Integration tests for Figma wiring inside PipelineRunner.

These tests verify that the runtime exposes Figma MCP tools only when the
figma-agent-core configuration is present, and that figma_* tools can be
executed through the pipeline runner.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from runtime.engine.agent_loader import AgentLoader
from runtime.engine.llm_engine import LLMConfig, LLMEngine, LLMProvider
from runtime.engine.message_bus import MessageBus
from runtime.engine.pipeline_runner import PipelineRunner
from runtime.engine.state_manager import StateManager


def _make_runner(workspace_root: Path, mcp_enabled: bool = True) -> PipelineRunner:
    config = LLMConfig(provider=LLMProvider.MOCK, mcp_enabled=mcp_enabled)
    llm = LLMEngine(config=config)
    return PipelineRunner(
        loader=AgentLoader(".agent_loop"),
        llm=llm,
        bus=MessageBus(),
        state=StateManager(),
        workspace_root=str(workspace_root),
    )


def test_figma_available_when_configured() -> None:
    runner = _make_runner(Path.cwd())
    # This test assumes the local figma-agent-core/.env is configured.
    core_dir = Path(runner.workspace) / "figma-agent-core"
    assert core_dir.exists(), "figma-agent-core directory must exist for this test"
    assert runner.mcp_enabled is True
    assert runner.figma_available is True


def test_figma_category_exposed_when_available() -> None:
    runner = _make_runner(Path.cwd())
    categories = runner.get_mcp_categories()
    if runner.figma_available:
        assert "figma" in categories
    else:
        assert "figma" not in categories


def test_figma_category_hidden_when_mcp_disabled() -> None:
    runner = _make_runner(Path.cwd(), mcp_enabled=False)
    assert runner.figma_available is False
    assert runner.get_mcp_categories() == []


def test_execute_mcp_figma_tool_dry_run() -> None:
    runner = _make_runner(Path.cwd())

    async def _run():
        return await runner.execute_mcp_tool("figma_run_pipeline", {"dry_run": True})

    result = asyncio.run(_run())
    assert result.get("mcp_executed") is True
    assert result["tool"] == "figma_run_pipeline"
    inner = result.get("result", {})
    assert inner.get("is_error") is False
    assert "content" in inner
    payload = inner["content"][0]["text"]
    assert "DRY RUN" in payload or "dry" in payload.lower()


def test_design_intake_short_circuits_for_full_code() -> None:
    runner = _make_runner(Path.cwd())

    async def _run():
        with patch.object(runner, "execute_mcp_tool", new=AsyncMock(return_value={
            "tool": "figma_run_pipeline",
            "result": {"status": "success", "returncode": 0, "stdout": "generated", "stderr": ""},
            "mcp_executed": True,
        })) as mock_mcp:
            result = await runner.run("сверстай макет Figma https://www.figma.com/design/abc123/Sample")
            mock_mcp.assert_awaited_once()
            args = mock_mcp.await_args[0]
            assert args[0] == "figma_run_pipeline"
            assert args[1].get("figma_url") == "https://www.figma.com/design/abc123/Sample"
            assert args[1].get("file_key") == "abc123"
        return result

    result = asyncio.run(_run())
    assert result.termination_status.value == "success"
    assert "Design pipeline triggered" in result.final_response


def test_design_intake_continues_planning_for_spec() -> None:
    runner = _make_runner(Path.cwd())

    async def _run():
        original_execute = runner.llm.execute

        async def _mock_execute(spec, inputs):
            response = await original_execute(spec, inputs)
            agent_path = getattr(spec, "source_path", "")
            if agent_path.endswith("user/design_intake.md"):
                response.parsed["design_descriptor"]["output_mode"] = "technical_assignment"
            return response

        with patch.object(runner.llm, "execute", new=_mock_execute):
            with patch.object(runner, "execute_mcp_tool", new=AsyncMock(return_value={})) as mock_mcp:
                result = await runner.run("напиши ТЗ по макету Figma https://www.figma.com/design/abc123/Sample")
                mock_mcp.assert_not_awaited()
        return result

    result = asyncio.run(_run())
    assert result.termination_status.value in ("success", "partial")


def test_extract_figma_file_key_and_node_id() -> None:
    runner = _make_runner(Path.cwd())
    assert runner._extract_figma_file_key("https://www.figma.com/design/abc123/Sample?node-id=1-2") == "abc123"
    assert runner._extract_figma_node_id("https://www.figma.com/design/abc123/Sample?node-id=1-2") == "1:2"
    assert runner._extract_figma_file_key("not a url") == ""
    assert runner._extract_figma_node_id("no node") == ""
