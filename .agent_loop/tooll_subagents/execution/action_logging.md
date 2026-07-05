# Action Logging

## Role
Immutable execution ledger that records every tool invocation, parameter snapshot, outcome hash, and side effect during the execution phase. Provides the forensic trail necessary for debugging, auditing, replay, and rollback.

## Contract

### Receives
- `execution_event`: structured record of a single tool call or significant system action
- `log_level`: enum (`debug`, `info`, `warning`, `error`, `critical`)
- `integrity_mode`: enum (`async`, `sync`) — whether caller blocks until log persisted
- `retention`: enum (`session`, `short_term`, `long_term`, `compliance`)

### Returns
- `log_entry_id`: unique identifier for this log entry
- `persisted_at`: timestamp when log was durably written
- `integrity_hash`: hash of the serialized log entry
- `replication_status`: enum (`local`, `replicated`, `quorum`) — durability level achieved

### Side Effects
- Writes to append-only log store (local or distributed)
- Triggers replication to secondary nodes if configured
- May trigger alerting if `log_level=critical`

## Decision Flow

1. **Validate event** — ensure `execution_event` contains actor, action, timestamp, and payload hash.
2. **Enrich metadata** — add sequence number, session ID, tool agent version, and environment fingerprint.
3. **Serialize** — convert to canonical JSON with deterministic key ordering.
4. **Compute integrity hash** — SHA-256 of serialized payload.
5. **Classify level** — determine `log_level` based on action severity (read=info, write=warning, delete=error, irreversible=critical).
6. **Write to store** — append to local log; fsync if `integrity_mode=sync`.
7. **Replicate** — if replication enabled, fan out to secondaries; wait for quorum if `integrity_mode=sync`.
8. **Apply retention** — schedule purge, archive, or compliance hold based on `retention` policy.
9. **Return** — emit `log_entry_id`, `persisted_at`, `integrity_hash`, `replication_status`.

## Failure Modes

| Condition | Response |
|---|---|
| Log store full or read-only | Buffer to emergency spill file; alert `control/resource_monitor.md`; retry every 10 s |
| Serialization produces non-deterministic output | Switch to canonical binary CBOR format; flag schema issue |
| Replication quorum unreachable | `replication_status=local`; retry with exponential backoff; alert if unconfirmed > 60 s |
| Clock skew detected | Reject event; request NTP sync; queue for retry |
| Critical event lost during crash | On recovery, scan execution trace buffers and backfill gaps; mark backfilled entries |
