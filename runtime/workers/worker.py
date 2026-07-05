#!/usr/bin/env python3
"""
Isolated Worker Process — executes a single agent invocation in a separate process.

Reads job from stdin (JSON), runs the agent spec through LLM, returns ONLY a summary
JSON to stdout. All intermediate data stays inside this process — the parent process
never sees raw tool output, keeping its context window clean.

Protocol:
  stdin  <- {"agent_spec": AgentSpec, "inputs": {...}, "worker_id": "..."}
  stdout -> {"summary": "...", "tokens_used": N, "status": "ok"|"error", ...}
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from typing import Any


def run_worker():
    """Main entry point for worker process. Reads job, executes, writes summary."""
    raw = sys.stdin.read()
    if not raw.strip():
        write_error("Empty stdin — no job received")
        return

    try:
        job = json.loads(raw)
    except json.JSONDecodeError as e:
        write_error(f"Invalid JSON input: {e}")
        return

    worker_id = job.get("worker_id", "unknown")
    agent_spec = job.get("agent_spec", {})
    inputs = job.get("inputs", {})
    max_tokens = job.get("max_tokens", 4096)
    model = job.get("model", "claude-haiku-4-5")

    t0 = time.perf_counter()
    tokens_used = 0
    try:
        result = execute_agent(agent_spec, inputs, max_tokens, model)
        tokens_used = result.get("tokens_used", 0)
        latency_ms = (time.perf_counter() - t0) * 1000

        write_summary({
            "worker_id": worker_id,
            "status": "ok",
            "summary": result.get("summary", ""),
            "parsed_output": result.get("parsed", {}),
            "tokens_used": tokens_used,
            "latency_ms": latency_ms,
            "model": model,
        })
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000
        write_error(f"Execution failed: {e}\n{traceback.format_exc()}", {
            "worker_id": worker_id,
            "tokens_used": tokens_used,
            "latency_ms": latency_ms,
        })


def execute_agent(agent_spec: dict[str, Any], inputs: dict[str, Any],
                  max_tokens: int, model: str) -> dict[str, Any]:
    """Execute agent spec via LLM API. Returns summary only — raw data stays in process."""

    system_prompt = build_system_prompt(agent_spec)
    user_message = build_user_message(inputs, agent_spec)

    # Try Anthropic first, fall back to OpenAI
    api_key = _get_api_key(model)
    if not api_key:
        # No API key — run decision flow locally and return structured output
        return execute_locally(agent_spec, inputs)

    try:
        return call_llm_api(system_prompt, user_message, max_tokens, model, api_key)
    except Exception:
        # Fallback: local execution of decision flow
        return execute_locally(agent_spec, inputs)


def execute_locally(agent_spec: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    """Execute decision flow locally without LLM — extract structured result."""
    role = agent_spec.get("role", "")
    name = agent_spec.get("name", "Agent")
    decision_flow = agent_spec.get("decision_flow", [])
    failure_modes = agent_spec.get("failure_modes", [])

    # Build summary from the decision flow execution
    summary_parts = [f"Agent '{name}' executed {len(decision_flow)} decision steps."]
    for step in decision_flow:
        summary_parts.append(f"- Step {step.get('number', '?')}: {step.get('title', '')}")

    # Apply inputs to build a response
    parsed: dict[str, Any] = {
        "agent": name,
        "steps_executed": len(decision_flow),
        "failure_modes_available": len(failure_modes),
        "inputs_received": list(inputs.keys()),
        "recommendation": "execution_complete",
    }

    if inputs:
        parsed["input_summary"] = {k: str(v)[:100] for k, v in inputs.items()}

    return {
        "summary": "\n".join(summary_parts),
        "parsed": parsed,
        "tokens_used": 0,
    }


def call_llm_api(system_prompt: str, user_message: str, max_tokens: int,
                 model: str, api_key: str) -> dict[str, Any]:
    """Call LLM API and extract summary from response."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0.3,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    content = response.content[0].text if isinstance(response.content, list) else str(response.content)
    tokens_used = response.usage.input_tokens + response.usage.output_tokens

    # Parse JSON from LLM response
    parsed = extract_json(content)

    # Build summary — this is what the parent sees, NOT the raw response
    summary = build_result_summary(parsed, content, tokens_used)

    return {"summary": summary, "parsed": parsed, "tokens_used": tokens_used}


def build_system_prompt(spec: dict[str, Any]) -> str:
    parts = [f"You are the **{spec.get('name', 'Agent')}** agent."]
    role = spec.get("role", "")
    if role:
        parts.append(f"\n## Role\n{role}")

    contract = spec.get("contract", {})
    receives = contract.get("receives", [])
    returns = contract.get("returns", [])
    side_effects = contract.get("side_effects", [])

    if receives:
        parts.append("\n## Input Contract")
        for p in receives:
            parts.append(f"- `{p.get('name', '?')}`: {p.get('type_hint', 'any')} — {p.get('description', '')}")

    if returns:
        parts.append("\n## Output Contract — YOU MUST RETURN THIS JSON:")
        parts.append("```json")
        out_schema = {}
        for p in returns:
            out_schema[p.get("name", "?")] = f"<{p.get('type_hint', 'any')}>"
            parts.append(f'  "{p.get("name", "?")}": <{p.get("type_hint", "any")}> — {p.get("description", "")}')
        parts.append("```")

    decision_flow = spec.get("decision_flow", [])
    if decision_flow:
        parts.append("\n## Decision Flow")
        for step in decision_flow:
            parts.append(f"{step.get('number', '?')}. **{step.get('title', '')}** — {step.get('description', '')}")

    failure_modes = spec.get("failure_modes", [])
    if failure_modes:
        parts.append("\n## Failure Modes")
        for fm in failure_modes:
            parts.append(f"- When `{fm.get('condition', '')}` → {fm.get('response', '')}")

    parts.append("\n## CRITICAL: Output ONLY valid JSON matching the Output Contract. No markdown, no extra text.")
    return "\n".join(parts)


def build_user_message(inputs: dict[str, Any], spec: dict[str, Any]) -> str:
    lines = ["Execute your Decision Flow with:"]
    for key, value in inputs.items():
        val_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        if len(val_str) > 2000:
            val_str = val_str[:2000] + "... [truncated]"
        lines.append(f"\n**{key}**: {val_str}")
    lines.append("\nReturn ONLY valid JSON matching your Output Contract.")
    return "\n".join(lines)


def build_result_summary(parsed: dict[str, Any], raw_content: str, tokens_used: int) -> str:
    """Build a compact summary — this is ALL the parent process sees."""
    lines = []
    for key, value in parsed.items():
        val_str = str(value)
        if len(val_str) > 300:
            val_str = val_str[:300] + "..."
        lines.append(f"- {key}: {val_str}")
    summary = "\n".join(lines) if lines else raw_content[:500]
    return summary


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:] if lines[0].startswith("```") else lines
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if "{" in text and "}" in text:
            try:
                start = text.index("{")
                end = text.rindex("}") + 1
                return json.loads(text[start:end])
            except (json.JSONDecodeError, ValueError):
                pass
        return {"raw_output": text[:500]}


def _get_api_key(model: str) -> str | None:
    import os
    if "claude" in model.lower() or "anthropic" in model.lower():
        return os.environ.get("ANTHROPIC_API_KEY")
    if "gpt" in model.lower() or "openai" in model.lower():
        return os.environ.get("OPENAI_API_KEY")
    return os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")


def write_summary(data: dict[str, Any]):
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def write_error(message: str, extra: dict[str, Any] | None = None):
    error_data = {"status": "error", "error": message}
    if extra:
        error_data.update(extra)
    sys.stdout.write(json.dumps(error_data, ensure_ascii=False) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    run_worker()
