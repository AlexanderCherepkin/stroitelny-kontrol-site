from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CompressionSummary:
    """Result of compressing a batch of traces."""
    summary: str
    original_count: int
    compressed_tokens_estimate: int
    fidelity_estimate: float
    timestamp: float = field(default_factory=time.time)


class ContextCompressor:
    """Summarizes pipeline iteration traces after every N steps.

    Keeps the parent's context window clean by replacing old detailed traces
    with a compact LLM-generated summary. Raw traces from tool agents can be
    thousands of tokens; the summary is typically under 200 tokens.
    """

    def __init__(
        self,
        llm_engine: Any,
        compress_every_n: int = 5,
        max_traces_to_keep: int = 2,
        target_summary_tokens: int = 200,
    ):
        self.llm = llm_engine
        self.compress_every_n = max(2, compress_every_n)
        self.max_traces_to_keep = max(0, max_traces_to_keep)
        self.target_summary_tokens = target_summary_tokens

        self._trace_buffer: list[dict[str, Any]] = []
        self._summaries: list[CompressionSummary] = []
        self._total_compressed = 0
        self._total_tokens_saved = 0

    def add_trace(self, trace: dict[str, Any]) -> None:
        """Buffer a raw trace for potential later compression."""
        self._trace_buffer.append(trace)

    def should_compress(self, iteration: int) -> bool:
        """Returns True if compression should run after this iteration."""
        return iteration > 0 and iteration % self.compress_every_n == 0

    async def compress(self) -> CompressionSummary | None:
        """Summarize buffered traces via LLM and return a summary record."""
        if not self._trace_buffer:
            return None

        original_count = len(self._trace_buffer)

        # Build a compact prompt for the LLM
        prompt = self._build_summary_prompt(self._trace_buffer)

        try:
            summary_text = await self._call_llm_summary(prompt)
        except Exception:
            # Fallback: manual compression
            summary_text = self._manual_summary(self._trace_buffer)

        summary = CompressionSummary(
            summary=summary_text,
            original_count=original_count,
            compressed_tokens_estimate=len(summary_text) // 4,
            fidelity_estimate=0.85,  # Heuristic
        )

        self._summaries.append(summary)
        self._total_compressed += original_count
        self._total_tokens_saved += self._estimate_saved_tokens(self._trace_buffer, summary_text)
        self._trace_buffer.clear()

        return summary

    def _build_summary_prompt(self, traces: list[dict[str, Any]]) -> str:
        lines = [
            "Summarize the following agent execution traces into a compact paragraph.",
            "Preserve: decisions made, errors encountered, tools used, outcomes.",
            "Discard: formatting details, redundant status messages, token counts.",
            f"Target length: ~{self.target_summary_tokens} tokens.",
            "",
            "Traces:",
        ]
        for t in traces:
            phase = t.get("phase", "unknown")
            agent = t.get("agent_path", "unknown")
            success = "OK" if t.get("success") else "FAIL"
            error = t.get("error", "")
            latency = t.get("latency_ms", 0)
            lines.append(f"  [{phase}] {agent} — {success} ({latency:.0f}ms)")
            outputs = t.get("outputs")
            if outputs and isinstance(outputs, dict):
                for key, val in outputs.items():
                    if key.startswith("_"):
                        continue  # Skip internal metadata
                    val_str = str(val)
                    if len(val_str) > 120:
                        val_str = val_str[:120] + "..."
                    lines.append(f"    {key}: {val_str}")
            if error:
                lines.append(f"    ERROR: {error}")
        return "\n".join(lines)

    async def _call_llm_summary(self, prompt: str) -> str:
        """Call the LLM engine to generate a summary."""
        if not self.llm:
            raise RuntimeError("No LLM engine available")

        # Use the LLM engine directly with a system prompt for summarization
        response = await self.llm.raw_chat_completion(
            system="You are a context compressor. Summarize execution traces concisely. "
                   "Preserve decisions, errors, tools used, and outcomes. "
                   "Return ONLY the summary text, no JSON, no markdown.",
            user=prompt,
            max_tokens=self.target_summary_tokens,
            temperature=0.2,
        )
        return response.strip()

    def _manual_summary(self, traces: list[dict[str, Any]]) -> str:
        """Fallback summarization without LLM."""
        phases = {}
        errors = []
        for t in traces:
            phase = t.get("phase", "unknown")
            agent = t.get("agent_path", "").split("/")[-1].replace(".md", "")
            success = t.get("success", True)
            phases.setdefault(phase, []).append(f"{agent}({ 'OK' if success else 'FAIL'})")
            if t.get("error"):
                errors.append(f"{agent}: {t['error'][:100]}")

        parts = []
        for phase, calls in phases.items():
            parts.append(f"{phase}: {', '.join(calls)}")
        summary = " | ".join(parts)
        if errors:
            summary += f" | Errors: {'; '.join(errors[:3])}"
        return summary

    def _estimate_saved_tokens(self, traces: list[dict[str, Any]], summary: str) -> int:
        """Estimate tokens kept out of the parent context."""
        raw_size = sum(len(str(t)) for t in traces)
        summary_size = len(summary)
        return max(0, (raw_size - summary_size) // 4)

    def get_compressed_trace(self) -> dict[str, Any] | None:
        """Returns a synthetic trace entry representing the latest summary."""
        if not self._summaries:
            return None
        latest = self._summaries[-1]
        return {
            "iteration": -1,
            "phase": "context_compression",
            "agent_path": "tools_memory/memory_store/context_compressor.md",
            "inputs": {"original_count": latest.original_count},
            "outputs": {
                "summary": latest.summary,
                "compressed_tokens": latest.compressed_tokens_estimate,
                "fidelity": latest.fidelity_estimate,
            },
            "latency_ms": 0,
            "success": True,
        }

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "total_compressed": self._total_compressed,
            "total_tokens_saved": self._total_tokens_saved,
            "summaries_generated": len(self._summaries),
            "buffer_size": len(self._trace_buffer),
        }
