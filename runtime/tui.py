#!/usr/bin/env python3
"""
Agentic Loop TUI — Rich-based terminal dashboard.

Shows live pipeline execution:
  - Agent execution tree
  - Progress bars for iterations / safety checks
  - Live logs from MessageBus audit events
  - Session stats

Usage:
    python -m runtime.tui --session <session_id>
    # Or launch from CLI: agentic-loop run "task" --tui
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.tree import Tree

from runtime.contracts.message import Message, MessageType
from runtime.engine.message_bus import MessageBus
from runtime.engine.state_manager import StateManager, OperationStatus


@dataclass
class TUIState:
    session_id: str = ""
    iteration: int = 0
    max_iterations: int = 5
    phase: str = "idle"
    agent_path: str = ""
    agents_visited: list[dict[str, Any]] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    status: str = "idle"


class AgenticTUI:
    """Rich-based live dashboard for pipeline execution."""

    def __init__(self, session_id: str | None = None, max_logs: int = 40):
        self.console = Console()
        self.state = TUIState(session_id=session_id or "")
        self.max_logs = max_logs
        self._running = False
        self._bus = MessageBus()
        self._state_mgr = StateManager()

        # Progress tracking
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=20),
            TaskProgressColumn(),
            console=self.console,
        )
        self._iter_task = self._progress.add_task("Iterations", total=5)
        self._safety_task = self._progress.add_task("Safety", total=16)

    async def start(self):
        self._running = True
        await self._bus.start()
        self._bus.subscribe("tui-monitor", self._on_message, [
            "phase.start",
            "phase.end",
            "agent.invoke",
        ])

    async def stop(self):
        self._running = False
        await self._bus.stop()
        self._state_mgr.close()

    async def _on_message(self, msg: Message):
        payload = msg.payload or {}
        topic = msg.topic or "unknown"

        if topic == "phase.start":
            phase = payload.get("phase", "unknown")
            self.state.phase = phase
            self._add_log(f"[PHASE START] {phase}")

        elif topic == "phase.end":
            phase = payload.get("phase", "unknown")
            self._add_log(f"[PHASE END  ] {phase}")

        elif topic == "agent.invoke":
            agent = payload.get("agent", "unknown")
            iteration = payload.get("iteration", 0)
            self.state.agent_path = agent
            self.state.iteration = max(self.state.iteration, iteration)
            self._progress.update(self._iter_task, completed=self.state.iteration)

    def _add_log(self, line: str):
        ts = time.strftime("%H:%M:%S")
        self.state.logs.append(f"{ts} {line}")
        if len(self.state.logs) > self.max_logs:
            self.state.logs.pop(0)

    def _build_tree(self) -> Tree:
        """Build agent execution tree."""
        root = Tree("[bold cyan]Agentic Loop Pipeline[/bold cyan]")

        # Session info
        session_node = root.add("[bold]Session[/bold]")
        session_node.add(f"ID: [dim]{self.state.session_id or 'none'}[/dim]")
        session_node.add(f"Status: [yellow]{self.state.status}[/yellow]")
        session_node.add(f"Elapsed: {self._fmt_elapsed()}")

        # Phase tree
        phases = {}
        for entry in self.state.agents_visited:
            phase = entry.get("phase", "unknown")
            agent = entry.get("agent", "unknown")
            ok = entry.get("success", True)
            status = "[green]OK[/green]" if ok else "[red]FAIL[/red]"
            phases.setdefault(phase, []).append(f"{agent} {status}")

        if phases:
            phases_node = root.add("[bold]Phases[/bold]")
            for phase, agents in phases.items():
                p_node = phases_node.add(f"[cyan]{phase}[/cyan]")
                for a in agents[:6]:
                    p_node.add(a)
                if len(agents) > 6:
                    p_node.add(f"[dim]... and {len(agents) - 6} more[/dim]")

        return root

    def _build_logs(self) -> Panel:
        text = "\n".join(self.state.logs) if self.state.logs else "[dim]Waiting for events...[/dim]"
        return Panel(text, title="[bold]Live Logs[/bold]", border_style="blue")

    def _build_progress(self) -> Panel:
        return Panel(self._progress, title="[bold]Progress[/bold]", border_style="green")

    def _build_layout(self) -> Table:
        """Compose the full TUI layout."""
        table = Table.grid(expand=True)
        table.add_column(ratio=2)
        table.add_column(ratio=3)

        top_row = Table.grid(expand=True)
        top_row.add_column(ratio=1)
        top_row.add_column(ratio=1)
        top_row.add_row(self._build_tree(), self._build_progress())

        table.add_row(top_row)
        table.add_row(self._build_logs())
        return table

    def _fmt_elapsed(self) -> str:
        sec = int(time.time() - self.state.start_time)
        return f"{sec // 60}m {sec % 60}s"

    async def run(self, poll_interval: float = 0.5):
        """Run the live TUI until stopped."""
        await self.start()
        try:
            with Live(self._build_layout(), console=self.console, refresh_per_second=4, screen=True) as live:
                while self._running:
                    # Poll session state for updates
                    if self.state.session_id:
                        self._poll_session()
                    live.update(self._build_layout())
                    await asyncio.sleep(poll_interval)
        finally:
            await self.stop()

    def _poll_session(self):
        """Poll StateManager for session updates."""
        r = self._state_mgr.read(f"session:{self.state.session_id}", scope="session")
        if r.status == OperationStatus.SUCCESS and r.value:
            val = r.value
            self.state.status = val.get("status", "unknown")
            self.state.iteration = val.get("iteration", self.state.iteration)

    def feed_event(self, event_type: str, payload: dict[str, Any]):
        """External entry point to feed events from PipelineRunner."""
        msg = Message(
            message_type=MessageType.EVENT,
            topic=event_type,
            payload=payload,
            sender="pipeline_runner",
        )
        asyncio.create_task(self._bus.publish(msg))


def cmd_dashboard(args: argparse.Namespace) -> int:
    """Launch TUI dashboard."""
    tui = AgenticTUI(session_id=args.session_id)
    try:
        asyncio.run(tui.run(poll_interval=args.poll_interval))
        return 0
    except KeyboardInterrupt:
        print("\n[TUI] Interrupted.")
        return 130


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="runtime.tui", description="Agentic Loop TUI Dashboard")
    p.add_argument("--session-id", default=None, help="Session to monitor")
    p.add_argument("--poll-interval", type=float, default=0.5, help="State poll interval (seconds)")
    p.set_defaults(func=cmd_dashboard)
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
