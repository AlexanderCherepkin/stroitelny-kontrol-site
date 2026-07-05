#!/usr/bin/env python3
"""
Agentic Loop Runtime — lightweight LLM-powered multi-agent execution engine.

Reads Markdown agent specifications from .agent_loop/ and executes them
as state machines via LLM API calls. Each agent spec becomes a system prompt,
the Contract inputs become the user message, and the LLM response is parsed
according to the Contract outputs.

Usage:
    python -m runtime.main "Your request here"
    python -m runtime.main --session-id abc123 "Continue previous work"
    python -m runtime.main --max-iterations 3 "Quick task"
    python -m runtime.main --provider openai --model gpt-4o "Query"

Environment variables:
    ANTHROPIC_API_KEY — required for Anthropic provider
    OPENAI_API_KEY    — required for OpenAI provider
    DEEPSEEK_API_KEY  — required for DeepSeek provider
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from runtime.engine.agent_loader import AgentLoader
from runtime.engine.llm_engine import LLMEngine, LLMConfig, LLMProvider
from runtime.engine.message_bus import MessageBus
from runtime.engine.pipeline_runner import PipelineRunner
from runtime.engine.state_manager import StateManager, OperationStatus
from runtime.contracts.message import Message, MessageType, DeliveryGuarantee, MessageStatus

# Optional TUI
try:
    from runtime.tui import AgenticTUI
    HAS_TUI = True
except ImportError:
    HAS_TUI = False


def resolve_root() -> Path:
    candidates = [
        Path(os.getenv("AGENT_LOOP_ROOT", "")),
        Path(__file__).resolve().parent.parent / ".agent_loop",
        Path.cwd() / ".agent_loop",
    ]
    for c in candidates:
        if (c / "main_loop.md").exists():
            return c
    raise FileNotFoundError(
        "Cannot find .agent_loop/ directory. "
        "Set AGENT_LOOP_ROOT environment variable or run from the project root."
    )


def parse_args():
    p = argparse.ArgumentParser(
        description="Agentic Loop Runtime — lightweight LLM-powered multi-agent execution engine"
    )
    p.add_argument("request", nargs="?", help="User request to process")
    p.add_argument("--session-id", default=None, help="Session ID (resume existing or start new)")
    p.add_argument("--max-iterations", type=int, default=5, help="Max ReAct loop iterations")
    p.add_argument("--provider", default="anthropic",
                   choices=["anthropic", "openai", "deepseek", "mock"],
                   help="LLM provider (mock = deterministic responses without API keys)")
    p.add_argument("--model", default=None, help="Model name override")
    p.add_argument("--agent-loop-root", default=None,
                   help="Path to .agent_loop/ directory")
    p.add_argument("--list-agents", action="store_true",
                   help="List all loaded agents and exit")
    p.add_argument("--demo", action="store_true",
                   help="Run demo mode — execute main_loop with a sample request")
    p.add_argument("--state-db", default=None,
                   help="Path to SQLite state database (default: .agent_loop/data/state.db)")
    p.add_argument("--validate", action="store_true",
                   help="Validate runtime components without API keys (no LLM calls)")
    p.add_argument("--tui", action="store_true",
                   help="Launch TUI dashboard during execution")
    p.add_argument("--json-stream", action="store_true",
                   help="Stream NDJSON progress events to stdout for external dashboards")
    return p.parse_args()


async def main():
    args = parse_args()

    root = Path(args.agent_loop_root) if args.agent_loop_root else resolve_root()
    print(f"[Runtime] Agent loop root: {root}")

    loader = AgentLoader(root)

    if args.list_agents:
        agents = loader.load_all_agents()
        print(f"\nLoaded {len(agents)} agents:\n")
        for path, spec in sorted(agents.items()):
            steps = len(spec.decision_flow)
            failures = len(spec.failure_modes)
            print(f"  {path}")
            print(f"    Role: {spec.role[:80]}...")
            print(f"    Decision steps: {steps}, Failure modes: {failures}")
        return

    # Persistent state DB — sessions survive CLI restarts
    if args.state_db:
        state_path = args.state_db
    else:
        state_dir = root.parent / ".agent_loop" / "data"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = str(state_dir / "state.db")

    model = args.model or {"anthropic": "claude-sonnet-4-6", "openai": "gpt-4o", "deepseek": "deepseek-chat", "mock": "mock-engine"}[args.provider]
    config = LLMConfig(provider=LLMProvider(args.provider), model=model)
    llm = LLMEngine(config)
    bus = MessageBus()
    state = StateManager(db_path=state_path)

    # NDJSON stream subscriber for external dashboards (Node.js TUI)
    if args.json_stream:
        async def _ndjson_subscriber(msg):
            try:
                import json as _json
                event = {
                    "t": msg.topic or "unknown",
                    "ts": int(time.time() * 1000),
                    "payload": msg.payload or {},
                }
                line = _json.dumps(event, ensure_ascii=False) + "\n"
                sys.stdout.write(line)
                sys.stdout.flush()
            except Exception:
                pass

        bus.subscribe("ndjson-stream", _ndjson_subscriber, topics=[
            "phase.start", "phase.end", "agent.invoke",
        ])

    runner = PipelineRunner(loader=loader, llm=llm, bus=bus, state=state)

    if args.validate:
        print("=== Runtime Component Validation ===\n")

        # 1. AgentLoader
        print("1. AgentLoader: parsing all agents from .agent_loop/ ...")
        agents = loader.load_all_agents()
        print(f"   Loaded {len(agents)} agents")
        errors = []
        for path, spec in sorted(agents.items()):
            if not spec.name:
                errors.append(f"  MISSING_NAME: {path}")
            if not spec.role:
                errors.append(f"  MISSING_ROLE: {path}")
            if not spec.decision_flow:
                errors.append(f"  NO_DECISION_FLOW: {path}")
        if errors:
            for e in errors:
                print(f"   WARN: {e}")
        else:
            print(f"   All agents have name + role + decision flow")

        # Stats
        total_steps = sum(len(spec.decision_flow) for spec in agents.values())
        total_failures = sum(len(spec.failure_modes) for spec in agents.values())
        print(f"   Total decision steps: {total_steps}, total failure modes: {total_failures}")

        # 2. MessageBus
        print("\n2. MessageBus: topic routing + delivery guarantees ...")
        received = []
        async def test_subscriber(msg):
            received.append(msg.payload)

        await bus.start()
        bus.subscribe("test-1", test_subscriber, ["test.topic"])
        receipt = await bus.publish(Message(
            payload={"key": "value"},
            message_type=MessageType.EVENT,
            topic="test.topic",
            sender="validator",
            delivery_guarantee=DeliveryGuarantee.AT_LEAST_ONCE,
        ))
        await bus.stop()

        print(f"   Delivery status: {receipt.status.value}")
        print(f"   Messages received: {len(received)}")
        assert len(received) == 1, "Subscriber should receive 1 message"
        print(f"   Topic routing: OK")

        # Test dead-letter for unsubscribed topic
        await bus.start()
        dl_receipt = await bus.publish(Message(
            payload={"orphan": True},
            message_type=MessageType.EVENT,
            topic="no.subscribers.here",
            sender="validator",
        ))
        await bus.stop()
        print(f"   Dead-letter for orphan topic: {dl_receipt.status.value}")
        assert dl_receipt.status == MessageStatus.DEAD_LETTERED
        print(f"   Dead-letter queue: OK")

        # 3. StateManager
        print("\n3. StateManager: CRUD + optimistic concurrency + checkpoint/restore ...")

        # Clean up from any previous aborted run
        state.delete("test_key", scope="test", hard=True)
        state.delete("test_key2", scope="test", hard=True)

        r = state.create("test_key", {"data": "hello"}, scope="test")
        print(f"   Create: {r.status.value} (v{r.version})")
        assert r.status == OperationStatus.SUCCESS

        r2 = state.read("test_key", scope="test")
        print(f"   Read: {r2.status.value} = {r2.value}")
        assert r2.value == {"data": "hello"}

        r3 = state.update("test_key", {"data": "world"}, expected_version=1, scope="test")
        print(f"   Update (v1->v2): {r3.status.value}")
        assert r3.status == OperationStatus.SUCCESS
        assert r3.version == 2

        r4 = state.update("test_key", {"data": "conflict"}, expected_version=1, scope="test")
        print(f"   Optimistic concurrency conflict: {r4.status.value}")
        assert r4.status == OperationStatus.CONFLICT

        ckpt_id = state.checkpoint("test_session")
        print(f"   Checkpoint created: {ckpt_id[:12]}...")

        r5 = state.delete("test_key", scope="test")
        print(f"   Soft delete: {r5.status.value}")

        r6 = state.read("test_key", scope="test")
        print(f"   Read after delete: {r6.status.value}")
        assert r6.status == OperationStatus.NOT_FOUND

        r7 = state.restore(checkpoint_id=ckpt_id)
        print(f"   Restore from checkpoint: {r7.status.value}")
        assert r7.status == OperationStatus.SUCCESS

        r8 = state.read("test_key", scope="test")
        print(f"   Read after restore: {r8.status.value} = {r8.value}")
        assert r8.value == {"data": "world"}

        # Cleanup test data
        state.delete("test_key", scope="test", hard=True)
        state.close()

        print("\n=== All validations passed ===")
        print(f"Components ready. Use --demo or interactive mode with LLM API keys.")
        return

    if args.demo:
        request = args.request or "Analyze the current project structure and summarize what you find."
        print(f"\n[Demo] Running with request: {request}\n")

        tui_task = None
        if args.tui and HAS_TUI:
            tui = AgenticTUI()
            tui_task = asyncio.create_task(tui.run(poll_interval=0.5))

        print("=" * 60)
        try:
            result = await runner.run(request, max_iterations=args.max_iterations)
        except Exception as e:
            raise
        print("=" * 60)

        if tui_task:
            tui._running = False
            try:
                await asyncio.wait_for(tui_task, timeout=2.0)
            except asyncio.TimeoutError:
                pass

        print(f"\nStatus: {result.termination_status.value}")
        print(f"Iterations: {result.session_metrics.iterations}")
        print(f"Safety checks: {result.session_metrics.safety_checks_passed} passed, "
              f"{result.session_metrics.safety_checks_failed} failed")
        print(f"Time: {result.session_metrics.time_elapsed_ms:.0f}ms")
        print(f"\nTrace ({len(result.trace)} agent invocations):")
        for t in result.trace:
            status = "OK" if t.success else f"FAIL: {t.error}"
            print(f"  [{t.phase}] {t.agent_path} — {t.latency_ms:.0f}ms {status}")
        print(f"\nResponse:\n{result.final_response[:500]}")
        return

    if not args.request:
        print("Entering interactive mode. Type 'exit' to quit, 'help' for commands.")
        session_id = args.session_id
        while True:
            try:
                user_input = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                break
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                break
            if user_input.lower() == "help":
                print("Commands: exit/quit/q — leave; stats — session info; help — this message")
                continue
            if user_input.lower() == "stats":
                keys = state.list_keys("session")
                print(f"Sessions: {len(keys)} active")
                for k in keys:
                    r = state.read(k, "session")
                    if r.status.value == "success":
                        print(f"  {k}: v{r.version}")
                continue
            print(f"[Runtime] Processing...")
            try:
                result = await runner.run(user_input, session_id=session_id,
                                          max_iterations=args.max_iterations)
            except Exception as e:
                raise
            session_id = result.session_metrics.session_id
            print(f"[{result.termination_status.value}] {result.final_response[:300]}")
    else:
        try:
            result = await runner.run(args.request, session_id=args.session_id,
                                      max_iterations=args.max_iterations)
        except Exception as e:
            raise
        print(json.dumps({
            "status": result.termination_status.value,
            "session_id": result.session_metrics.session_id,
            "iterations": result.session_metrics.iterations,
            "time_ms": result.session_metrics.time_elapsed_ms,
            "response": result.final_response,
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
