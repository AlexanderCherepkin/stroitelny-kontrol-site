"""End-to-end integration tests for Agentic Loop runtime.

Runs the full ReAct pipeline with MockLLMEngine — no API keys required.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.engine.agent_loader import AgentLoader
from runtime.engine.llm_engine import LLMEngine, LLMConfig, LLMProvider
from runtime.engine.message_bus import MessageBus
from runtime.engine.pipeline_runner import PipelineRunner, TerminationStatus
from runtime.engine.state_manager import StateManager


def _resolve_root() -> Path:
    candidates = [
        Path(__file__).resolve().parent.parent.parent / ".agent_loop",
        Path.cwd() / ".agent_loop",
    ]
    for c in candidates:
        if (c / "main_loop.md").exists():
            return c
    raise FileNotFoundError("Cannot find .agent_loop/ directory")


async def _run_pipeline(request: str, max_iterations: int = 2):
    root = _resolve_root()
    loader = AgentLoader(root)
    llm = LLMEngine(LLMConfig(provider=LLMProvider.MOCK, model="mock-engine"))
    bus = MessageBus()
    state = StateManager(db_path=":memory:")
    runner = PipelineRunner(loader=loader, llm=llm, bus=bus, state=state)
    return await runner.run(request, max_iterations=max_iterations)


def test_mock_pipeline_completes():
    """Full ReAct pipeline with mock provider should finish in <1s."""
    result = asyncio.run(_run_pipeline("test task", max_iterations=2))

    assert result is not None
    assert result.termination_status == TerminationStatus.SUCCESS
    assert result.session_metrics.iterations >= 1
    assert result.session_metrics.time_elapsed_ms > 0
    assert len(result.trace) >= 20


def test_mock_pipeline_safety_pre_check():
    """Safety pre-check agents should all pass with mock responses."""
    result = asyncio.run(_run_pipeline("test task", max_iterations=1))

    assert result is not None
    safety_pre = [t for t in result.trace if t.phase == "safety_pre_check"]
    assert len(safety_pre) == 5
    assert all(t.success for t in safety_pre)
    assert result.session_metrics.safety_checks_failed == 0


def test_mock_pipeline_trace_structure():
    """Every trace entry must have required fields."""
    result = asyncio.run(_run_pipeline("test task", max_iterations=2))

    for entry in result.trace:
        assert isinstance(entry.iteration, int)
        assert isinstance(entry.phase, str)
        assert isinstance(entry.agent_path, str)
        assert entry.latency_ms >= 0
        assert isinstance(entry.success, bool)


def test_mock_pipeline_state_persisted():
    """StateManager should persist session data."""
    root = _resolve_root()
    loader = AgentLoader(root)
    llm = LLMEngine(LLMConfig(provider=LLMProvider.MOCK, model="mock-engine"))
    bus = MessageBus()
    state = StateManager(db_path=":memory:")
    runner = PipelineRunner(loader=loader, llm=llm, bus=bus, state=state)

    result = asyncio.run(runner.run("state test", max_iterations=1))
    session_key = f"session:{result.session_metrics.session_id}"
    read_result = state.read(session_key, scope="session")

    assert read_result.status.value == "success"
    assert read_result.value.get("status") in ("completed", "running")


def test_mock_llm_engine_returns_parsed_json():
    """MockLLMEngine should return deterministic parsed JSON per agent."""
    from runtime.contracts.agent_spec import AgentSpec

    spec = AgentSpec(name="Test", role="test", decision_flow=[], failure_modes=[])
    spec.source_path = "safety-control/input_sanitizer.md"

    llm = LLMEngine(LLMConfig(provider=LLMProvider.MOCK))
    response = asyncio.run(llm.execute(spec, {"raw_user_input": "hello"}))

    assert response.parsed is not None
    assert response.parsed.get("blocked") is False
    assert response.model == "mock-engine"
    assert response.latency_ms >= 0


def test_mock_termination_on_second_iteration():
    """Recursion/termination agent should terminate on iteration >= 2."""
    result = asyncio.run(_run_pipeline("terminate test", max_iterations=3))

    assert result is not None
    assert result.session_metrics.iterations <= 2
    assert result.termination_status == TerminationStatus.SUCCESS
