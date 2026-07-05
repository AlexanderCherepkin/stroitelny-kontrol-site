# Memanto Recall

## Role
Observation-layer agent that retrieves relevant, previously stored semantic memories from Memanto to enrich the current ReAct context. Acts as an active RAG replacement: instead of injecting a static memory blob, it queries for exactly what the current agent needs.

## Contract

### Receives
- `query`: natural-language search string
- `agent_id`: string | None — defaults to `MEMANTO_AGENT_ID` or `agentic_loop`
- `memory_type`: list of types to filter, or None
- `tags`: list of tags to filter, or None
- `limit`: integer — max results (default 5)
- `min_confidence`: float | None — confidence floor
- `context_hint`: string | None — short description of why the memory is needed (used to refine the query if Memanto supports it)

### Returns
- `memories`: list of retrieved memory records with `id`, `title`, `content`, `type`, `tags`, `confidence`, `source_ref`
- `total_found`: integer
- `availability`: boolean
- `status`: enum (`complete`, `degraded`, `failed`)
- `fallback_reason`: string | None

### Side Effects
- Calls `memanto_recall` MCP tool or `runtime/engine/memanto_client.py`
- Logs query and result count to `audit_logger.md`

## Decision Flow

1. **Validate query** — reject empty queries with `status=failed`.
2. **Build query** — use `query`; if `context_hint` is provided, append it for specificity.
3. **Set filters** — apply `memory_type`, `tags`, `limit`, and `min_confidence` when provided.
4. **Execute recall** — call `memanto_recall` with the constructed request.
5. **Handle degradation** — if Memanto is unavailable, search the in-memory fallback store by substring match and report `status=degraded`.
6. **Rank and format** — order results by confidence/recency; keep only fields needed by the requesting agent.
7. **Return** — emit memories, total_found, availability, status, and fallback_reason.

## Failure Modes

| Condition | Response |
|---|---|
| Memanto server unreachable | `status=degraded`; search fallback store; log reason; continue |
| Empty query | `status=failed`; return empty memories |
| No results found | `status=complete`; return empty list; do not treat as failure |
| Query too large | Truncate query to 500 chars; log warning |
| Malformed Memanto response | Parse what is possible; log anomaly to `mutual_check/anomaly_detector.md` |
