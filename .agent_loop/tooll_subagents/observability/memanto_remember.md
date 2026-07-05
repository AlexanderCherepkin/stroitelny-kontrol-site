# Memanto Remember

## Role
Observation-layer agent that persists important facts, decisions, constraints, and lessons from the current ReAct iteration into the Memanto semantic memory layer. Replaces or augments plaintext memory writes when long-term, queryable recall is required.

## Contract

### Receives
- `memory_payload`: text or structured content to store
- `memory_type`: enum (`instruction`, `fact`, `decision`, `goal`, `commitment`, `preference`, `relationship`, `context`, `event`, `learning`, `observation`, `artifact`, `error`) — defaults to `fact`
- `title`: short title for the memory (defaults to first 80 chars of content)
- `tags`: list of keywords for filtering
- `confidence`: float 0–1 — defaults to 0.8
- `agent_id`: string | None — Memanto namespace identifier; defaults to `MEMANTO_AGENT_ID` or `agentic_loop`
- `source`: string — defaults to `agent`
- `source_ref`: string | None — file path, tool name, or audit anchor

### Returns
- `memory_id`: ID assigned by Memanto or fallback store
- `status`: enum (`stored`, `degraded`, `failed`)
- `availability`: boolean — whether Memanto server responded
- `fallback_reason`: string | None — reason for degraded/failed state

### Side Effects
- Calls `memanto_remember` MCP tool or `runtime/engine/memanto_client.py`
- Logs operation to `audit_logger.md`

## Decision Flow

1. **Validate payload** — ensure content is non-empty and within 10 000 characters; truncate if necessary.
2. **Infer type** — if `memory_type` is missing, classify content as `fact` for plain observations, `decision` for chosen plans, `constraint` for policies, `learning` for failure/recovery lessons.
3. **Select target** — use `agent_id` override if provided; otherwise use environment/agentic default.
4. **Ensure namespace** — if this is the first Memanto write in the session, invoke `memanto_create_agent` to create the namespace.
5. **Store memory** — call `memanto_remember` with title, type, tags, confidence, source, and source_ref.
6. **Handle degradation** — if Memanto is unavailable, write to in-memory fallback store and report `status=degraded`.
7. **Return** — emit memory_id, status, availability, and fallback_reason.

## Failure Modes

| Condition | Response |
|---|---|
| Memanto server unreachable | `status=degraded`; store in fallback; log to `audit_logger.md`; continue |
| Payload exceeds size limit | Truncate to 10 000 chars with ellipsis; store truncated version; log warning |
| Missing content | `status=failed`; return error; no side effects |
| Duplicate memory detected by Memanto | Use returned existing `memory_id`; log deduplication |
| Namespace creation fails | Degrade to fallback store; escalate to `control/human_oversight.md` if persistent |
