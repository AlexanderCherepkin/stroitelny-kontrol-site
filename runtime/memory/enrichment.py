#!/usr/bin/env python3
"""
Memory Enrichment — extracts structured facts from a session trace / result.

Runs after each pipeline session to distill durable knowledge:
  - user facts (preferences, role, constraints)
  - project facts (decisions, architecture changes)
  - feedback facts (what worked, what was rejected)
  - reference facts (links, commands, file paths)

Can use LLM summarization when available; falls back to heuristics.
"""

from __future__ import annotations

import re
from typing import Any


class MemoryEnrichment:
    """Extracts MemoryEntry records from a completed session."""

    MEMORY_TYPE_ORDER = ["user", "feedback", "project", "reference"]

    def __init__(self, llm_engine: Any | None = None):
        self.llm = llm_engine

    def extract(self, session_data: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Given session result dict, return a list of memory entries.
        Each entry: {id, type, title, body, tags, priority, source}
        """
        facts: list[dict[str, Any]] = []
        user_input = session_data.get("user_input", "")
        final_response = session_data.get("final_response", "")
        trace = session_data.get("trace", [])
        metrics = session_data.get("metrics", {})
        status = session_data.get("termination_status", "")

        # 1. User intent / preference fact
        if user_input:
            facts.append(self._make_entry(
                type_="user",
                title=f"Session intent: {self._truncate(user_input, 60)}",
                body=user_input,
                tags=["intent", "user", "session"],
                priority=7,
                source="enrichment.session_intent",
            ))

        # 2. Project fact — if output looks like a decision / architecture note
        if final_response and len(final_response) > 20:
            facts.append(self._make_entry(
                type_="project",
                title=f"Session output: {self._truncate(final_response, 60)}",
                body=final_response,
                tags=["output", "project", "session"],
                priority=6,
                source="enrichment.session_output",
            ))

        # 3. Extract safety findings as feedback
        for t in trace:
            if not isinstance(t, dict):
                continue
            phase = t.get("phase", "")
            if phase == "safety_pre_check":
                outputs = t.get("outputs") or {}
                if outputs.get("blocked") or outputs.get("status") == "blocked":
                    facts.append(self._make_entry(
                        type_="feedback",
                        title="Safety gate blocked a request",
                        body=f"Phase {phase} blocked. Inputs: {t.get('inputs', {})}",
                        tags=["safety", "blocked", "feedback"],
                        priority=8,
                        source="enrichment.safety",
                    ))

        # 4. Agent invocation patterns (which agents were used)
        agents_visited: set[str] = set()
        for t in trace:
            ap = t.get("agent_path", "") if isinstance(t, dict) else ""
            if ap:
                agents_visited.add(ap)
        if agents_visited:
            facts.append(self._make_entry(
                type_="project",
                title=f"Agents visited in session ({len(agents_visited)})",
                body="\n".join(sorted(agents_visited)),
                tags=["agents", "trace", "project"],
                priority=4,
                source="enrichment.agent_trace",
            ))

        # 5. Tool usage metrics
        tools = metrics.get("tools_used", []) if isinstance(metrics, dict) else []
        if tools:
            facts.append(self._make_entry(
                type_="reference",
                title=f"Tools used: {', '.join(tools[:5])}",
                body=f"Tools used in session: {tools}",
                tags=["tools", "metrics", "reference"],
                priority=3,
                source="enrichment.metrics",
            ))

        # 6. Failure / escalation as high-priority feedback
        if status in ("failure", "escalated_human"):
            facts.append(self._make_entry(
                type_="feedback",
                title=f"Session ended with status: {status}",
                body=f"Final status: {status}\nUser input: {user_input}",
                tags=["failure", "escalation", "feedback"],
                priority=9,
                source="enrichment.status",
            ))

        # 7. Markdown wikilink extraction from any text
        all_text = f"{user_input}\n{final_response}"
        for link in self._extract_wikilinks(all_text):
            facts.append(self._make_entry(
                type_="reference",
                title=f"Reference: {link}",
                body=f"Linked memory: [[{link}]]",
                tags=["link", "reference", "wikilink"],
                priority=5,
                source="enrichment.wikilink",
            ))

        # If LLM available, ask it to summarize in one extra fact
        if self.llm and final_response:
            summary = self._llm_summarize(user_input, final_response)
            if summary:
                facts.append(self._make_entry(
                    type_="project",
                    title=f"Summary: {self._truncate(summary, 60)}",
                    body=summary,
                    tags=["summary", "llm", "project"],
                    priority=7,
                    source="enrichment.llm_summary",
                ))

        return facts

    def _make_entry(self, type_: str, title: str, body: str, tags: list[str],
                    priority: int, source: str) -> dict[str, Any]:
        import uuid
        return {
            "id": f"{type_}_{uuid.uuid4().hex[:8]}",
            "type": type_,
            "title": title,
            "body": body,
            "tags": [t.lower().strip() for t in tags[:10]],
            "priority": max(1, min(10, priority)),
            "source": source,
        }

    def _truncate(self, text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[: max_len - 3].rstrip() + "..."

    def _extract_wikilinks(self, text: str) -> list[str]:
        return re.findall(r"\[\[([^\]]+)\]\]", text)

    def _llm_summarize(self, user_input: str, final_response: str) -> str | None:
        """Optional LLM-based fact extraction."""
        try:
            # Minimal contract: assume llm_engine has execute() returning content string
            prompt = (
                "Extract one concise factual sentence describing what was done or decided.\n"
                f"User request: {user_input[:500]}\n"
                f"Assistant response: {final_response[:500]}\n"
                "Fact:"
            )
            # Try raw_chat_completion if available (added in Phase 4)
            if hasattr(self.llm, "raw_chat_completion"):
                resp = self.llm.raw_chat_completion(prompt)
                if resp:
                    return resp.strip()
            # Fallback: execute with a dummy AgentSpec
            from ..contracts.agent_spec import AgentSpec
            spec = AgentSpec(
                name="enrichment_summarizer",
                role="Summarize session into one fact.",
                decision_flow=[],
                failure_modes=[],
                contract=None,
            )
            result = self.llm.execute(spec, {"prompt": prompt})
            if result and result.parsed:
                return str(result.parsed.get("summary", result.parsed)).strip()
        except Exception:
            pass
        return None
