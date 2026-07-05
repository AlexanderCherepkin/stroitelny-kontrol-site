# Mem0 Remember

## Role
Observation-layer agent that persists important facts, decisions, constraints, and lessons from the current ReAct iteration into the Mem0 long-term memory layer. Mem0 automatically extracts key facts from conversational messages, embeds them, and stores them for later retrieval.

## Contract

### Receives
- `memory_payload`: text or structured content to store; can be a user message, assistant reply, or list of turns
- `memory_type`: enum (`semantic`, `episodic`, `procedural`) — defaults to `semantic`; Mem0 OSS currently treats `procedural_memory` specially when `agent_id` is present
- `user_id`: string | None — entity scope; defaults to `MEM0_USER_ID` or `agentic_loop`
- `agent_id`: string | None — entity scope; defaults to `MEM0_AGENT_ID` or `agentic_loop`
- `run_id`: string | None — entity scope; defaults to `MEM0_RUN_ID`
- `metadata`: dict | None — additional structured metadata to attach
- `infer`: bool — whether Mem0 should extract facts automatically (default true)
- `source`: string — defaults to `agent`
- `source_ref`: string | None — file path, tool name, or audit anchor

### Returns
- `memory_ids`: list of IDs assigned by Mem0 or fallback store
- `status`: enum (`stored`, `degraded`, `failed`)
- `availability`: boolean — whether Mem0 responded
- `fallback_reason`: string | None — reason for degraded/failed state

### Side Effects
- Calls `mem0_add` MCP tool or `runtime/engine/mem0_client.py`
- Logs operation to `audit_logger.md`

## Decision Flow

1. **Validate payload** — ensure content is non-empty and within 10 000 characters; truncate if necessary.
2. **Infer type** — if `memory_type` is missing, default to `semantic` for facts and episodic for conversation turns.
3. **Build messages** — wrap `memory_payload` into Mem0 message format `[{"role": "user" | "assistant", "content": ...}]` when it represents a turn; otherwise pass as raw string.
4. **Set scope** — apply `user_id`, `agent_id`, `run_id`, and `metadata` filters.
5. **Store memory** — call `mem0_add` with messages, filters, metadata, and `infer` flag.
6. **Handle degradation** — if Mem0 is unavailable, write to in-memory fallback store and report `status=degraded`.
7. **Return** — emit memory_ids, status, availability, and fallback_reason.

## Failure Modes

| Condition | Response |
|---|---|
| Mem0 SDK/API unavailable | `status=degraded`; store in fallback; log to `audit_logger.md`; continue |
| Payload exceeds size limit | Truncate to 10 000 chars with ellipsis; store truncated version; log warning |
| Missing content | `status=failed`; return error; no side effects |
| Mem0 extraction returns no facts | `status=stored`; return empty memory_ids; note no facts extracted |
| Safety policy forbids storing this content | `status=failed`; do not persist; escalate to `control/human_oversight.md` |
