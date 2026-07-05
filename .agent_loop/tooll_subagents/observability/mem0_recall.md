# Mem0 Recall

## Role
Observation-layer agent that retrieves relevant, previously stored long-term memories from Mem0 to enrich the current ReAct context. Mem0 performs hybrid semantic + keyword + entity retrieval, so this agent is used as an active RAG replacement.

## Contract

### Receives
- `query`: natural-language search string
- `user_id`: string | None — entity scope; defaults to `MEM0_USER_ID` or `agentic_loop`
- `agent_id`: string | None — entity scope; defaults to `MEM0_AGENT_ID` or `agentic_loop`
- `run_id`: string | None — entity scope; defaults to `MEM0_RUN_ID`
- `limit`: integer — max results (default 5)
- `threshold`: float — minimum similarity score (default 0.1)
- `context_hint`: string | None — short description of why the memory is needed

### Returns
- `memories`: list of retrieved memory records with `id`, `memory`, `score`, `metadata`
- `total_found`: integer
- `availability`: boolean
- `status`: enum (`complete`, `degraded`, `failed`)
- `fallback_reason`: string | None

### Side Effects
- Calls `mem0_search` MCP tool or `runtime/engine/mem0_client.py`
- Logs query and result count to `audit_logger.md`

## Decision Flow

1. **Validate query** — reject empty queries with `status=failed`.
2. **Build query** — use `query`; if `context_hint` is provided, append it for specificity.
3. **Set filters** — apply `user_id`, `agent_id`, `run_id`, and `limit`/`threshold`.
4. **Execute recall** — call `mem0_search` with the constructed request.
5. **Handle degradation** — if Mem0 is unavailable, search the in-memory fallback store by substring match and report `status=degraded`.
6. **Rank and format** — order results by score; keep only fields needed by the requesting agent.
7. **Return** — emit memories, total_found, availability, status, and fallback_reason.

## Failure Modes

| Condition | Response |
|---|---|
| Mem0 SDK/API unavailable | `status=degraded`; search fallback store; log reason; continue |
| Empty query | `status=failed`; return empty memories |
| No results found | `status=complete`; return empty list; do not treat as failure |
| Query too large | Truncate query to 500 chars; log warning |
| Malformed Mem0 response | Parse what is possible; log anomaly to `mutual_check/anomaly_detector.md` |
