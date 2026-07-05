# Memanto Answer

## Role
Observation-layer agent that synthesizes a grounded answer from the Memanto memory store. Used at session boundaries or when a subagent needs a concise, memory-backed summary instead of raw retrieval results.

## Contract

### Receives
- `query`: the question to answer from memory (e.g. "What were the final acceptance criteria?")
- `agent_id`: string | None — defaults to `MEMANTO_AGENT_ID` or `agentic_loop`
- `memory_type`: list of types to scope the answer, or None
- `tags`: list of tags to scope the answer, or None

### Returns
- `answer`: string — generated answer or empty string if unavailable
- `sources`: list of memory IDs/titles used as grounding
- `availability`: boolean
- `status`: enum (`complete`, `degraded`, `failed`)
- `fallback_reason`: string | None

### Side Effects
- Calls `memanto_answer` MCP tool or `runtime/engine/memanto_client.py`
- Logs query and answer length to `audit_logger.md`

## Decision Flow

1. **Validate query** — reject empty queries with `status=failed`.
2. **Scope answer** — apply optional `memory_type` and `tags` filters.
3. **Generate answer** — call `memanto_answer`; the Memanto server performs retrieval + LLM grounding internally.
4. **Handle degradation** — if Memanto is unavailable, perform a local `memanto_recall` and synthesize a short answer from the top results, marking `status=degraded`.
5. **Validate output** — run the answer through `safety-control/data_leak_preventer.md` before returning it to the caller.
6. **Return** — emit answer, sources, availability, status, and fallback_reason.

## Failure Modes

| Condition | Response |
|---|---|
| Memanto server unreachable | `status=degraded`; fall back to recall + local synthesis; log reason |
| Empty query | `status=failed`; return empty answer |
| Answer blocked by safety layer | Redact sensitive content; return sanitized answer with notice |
| Memanto returns empty answer | `status=complete`; return empty answer and note insufficient memory |
| Safety scan unavailable | Return answer with warning; do not block execution |
