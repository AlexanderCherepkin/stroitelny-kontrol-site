# Mem0 List

## Role
Observation-layer agent that lists all long-term memories stored in Mem0 for the current entity scope. Used for session summaries, audits, and debugging memory contents.

## Contract

### Receives
- `user_id`: string | None — entity scope; defaults to `MEM0_USER_ID` or `agentic_loop`
- `agent_id`: string | None — entity scope; defaults to `MEM0_AGENT_ID` or `agentic_loop`
- `run_id`: string | None — entity scope; defaults to `MEM0_RUN_ID`
- `limit`: integer — max results (default 20)

### Returns
- `memories`: list of stored memory records with `id`, `memory`, `metadata`, `created_at`
- `total_found`: integer
- `availability`: boolean
- `status`: enum (`complete`, `degraded`, `failed`)
- `fallback_reason`: string | None

### Side Effects
- Calls `mem0_get_all` MCP tool or `runtime/engine/mem0_client.py`
- Logs operation to `audit_logger.md`

## Decision Flow

1. **Set scope** — apply `user_id`, `agent_id`, `run_id`, and `limit`.
2. **Execute list** — call `mem0_get_all`.
3. **Handle degradation** — if Mem0 is unavailable, return entries from the in-memory fallback store and report `status=degraded`.
4. **Format** — normalize record shape and metadata.
5. **Return** — emit memories, total_found, availability, status, and fallback_reason.

## Failure Modes

| Condition | Response |
|---|---|
| Mem0 SDK/API unavailable | `status=degraded`; list fallback store; log reason; continue |
| No memories found | `status=complete`; return empty list |
| Malformed Mem0 response | Parse what is possible; log anomaly to `mutual_check/anomaly_detector.md` |
