# Audit Logger

## Role
Immutable record-keeping agent that captures every decision, transformation, and handoff across all layers of the Agentic Loop. Provides forensic traceability, non-repudiation, and chronological replay capability for the entire system.

## Contract

### Receives
- `event`: structured record containing actor, action, payload hash, timestamp, and layer origin
- `event_type`: enum (`input_received`, `safety_check`, `tool_invocation`, `result_emitted`, `error_raised`, `human_approval`, `policy_decision`)
- `integrity_mode`: enum (`async`, `sync`)
- `retention_policy`: enum (`session`, `short_term`, `long_term`, `compliance`)

### Returns
- `log_id`: unique immutable identifier for this record
- `timestamp`: ISO-8601 with microsecond precision
- `hash`: cryptographic hash of the serialized event
- `status`: enum (`logged`, `buffered`, `failed`)
- `replication_confirmations`: count of replicas that acknowledged the write

### Side Effects
- Persists event to append-only log store
- Replicates to secondary nodes if configured
- Triggers retention policy enforcement (archive or purge)

## Decision Flow

1. **Validate event structure** — ensure all required fields present; reject malformed events with error notification.
2. **Enrich metadata** — add system clock timestamp, sequence number, and layer topology coordinates.
3. **Serialize** — convert event to canonical JSON with deterministic key ordering.
4. **Compute hash** — generate SHA-256 of serialized payload for integrity verification.
5. **Write to primary log** — append to local append-only store; fsync if `integrity_mode=sync`.
6. **Replicate** — if replication configured, fan out to secondary nodes; wait for quorum if `integrity_mode=sync`.
7. **Apply retention policy** — schedule purge or archive based on `retention_policy` and regulatory requirements.
8. **Return confirmation** — emit `log_id`, `timestamp`, `hash`, `status`, `replication_confirmations`.

## Failure Modes

| Condition | Response |
|---|---|
| Log store full or read-only | `status=failed`, buffer to emergency spill file; alert `control/resource_monitor.md` |
| Replication quorum not reached | `status=buffered`, retry with exponential backoff; alert if unconfirmed > 60 s |
| Clock skew detected | Reject event, request NTP sync from `control/resource_monitor.md` |
| Serialization produces non-deterministic output | Switch to canonical binary format; flag schema issue |
| Retention policy conflict (compliance vs purge) | Preserve; escalate to `compliance_checker.md` for ruling |
