# State Manager

## Role
Persistent and ephemeral state custodian that manages session, agent, and pipeline state across the entire Agentic Loop. Ensures state consistency, supports recovery, enables observability, and provides atomic transitions to prevent race conditions and data loss.

## Contract

### Receives
- `state_operation`: enum (`create`, `read`, `update`, `delete`, `checkpoint`, `restore`, `archive`)
- `state_scope`: enum (`session`, `agent`, `pipeline`, `system`, `user_profile`)
- `state_key`: identifier for the specific state object
- `state_payload`: data to write or update (for create/update/checkpoint)
- `consistency_level`: enum (`eventual`, `session_strong`, `immediate`)

### Returns
- `operation_status`: enum (`success`, `not_found`, `conflict`, `timeout`, `corrupted`)
- `state_value`: the retrieved or updated state object (for read/update/restore)
- `version_id`: monotonic version or timestamp for optimistic concurrency
- `replication_status`: enum (`local`, `replicated`, `quorum`)

### Side Effects
- Reads/writes to session store, agent registry, or persistent backing store
- Triggers replication to secondary nodes if configured
- May invoke `control/resource_monitor.md` if store pressure detected

## Decision Flow

1. **Validate operation** — ensure `state_operation` is permitted for `state_scope` (e.g., `delete` not allowed for `system` scope without admin override).
2. **Resolve store** — select backing store based on `state_scope` and `consistency_level`: `session` → in-memory with async disk flush; `agent` → registry with versioning; `pipeline` → checkpoint store; `system` → strongly consistent distributed store; `user_profile` → long-term profile database.
3. **Apply concurrency control** — for `update` and `delete`, verify `version_id` matches current stored version; if mismatch, `operation_status=conflict` and return current version.
4. **Execute operation** —
   - `create`: initialize state with defaults, assign version 1, persist.
   - `read`: fetch state, deserialize, verify integrity hash; if corrupted, attempt restore from last checkpoint.
   - `update`: apply delta merge (preserve unmodified fields), increment version, write.
   - `delete`: soft-delete with tombstone marker; hard-delete only after retention policy expires.
   - `checkpoint`: atomically snapshot current state to checkpoint store with timestamp and session ID.
   - `restore`: load checkpoint by ID or latest for session; validate against schema; if corrupted, try previous checkpoint.
   - `archive`: move state to cold storage; compress and index for retrieval.
5. **Replicate** — if `consistency_level=immediate`, wait for quorum acknowledgment; if `session_strong`, wait for local + 1 replica; if `eventual`, enqueue replication asynchronously.
6. **Handle corruption** — if integrity check fails, attempt recovery from replica or checkpoint; if all sources fail, `operation_status=corrupted` and alert `anomaly_detector.md`.
7. **Return** — emit status, value, version, replication status.

## Failure Modes

| Condition | Response |
|---|---|
| Store unreachable (network partition) | `operation_status=timeout`, serve from local cache if `read` and cache valid; queue `write` for retry |
| Version conflict on concurrent update | `operation_status=conflict`, return current version and value; require caller to reconcile and retry |
| Checkpoint chain corrupted (all checkpoints invalid) | `operation_status=corrupted`, attempt baseline reconstruction from `audit_logger.md`; if fails, `state_value=null` |
| State payload exceeds size limit | Split into linked segments; return `state_value` with segment map; log segmentation |
| Replication quorum unreachable indefinitely | Degrade to `replication_status=local`; alert `resource_monitor.md` and `network_guard.md` |
| State scope permissions violated | `operation_status=conflict`, reject operation; log unauthorized access attempt to `audit_logger.md` |
