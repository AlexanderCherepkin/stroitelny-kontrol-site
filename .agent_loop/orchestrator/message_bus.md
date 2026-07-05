# Message Bus

## Role
Internal communication backbone that enables asynchronous, decoupled messaging between agents and layers. Provides publish/subscribe, request/reply, and broadcast patterns with guaranteed delivery, ordering controls, and dead-letter handling for failed deliveries.

## Contract

### Receives
- `message`: payload to send (any serializable structure)
- `message_type`: enum (`command`, `event`, `query`, `reply`, `broadcast`)
- `topic`: routing key or channel name (e.g., `safety.pre_check`, `execution.result`, `system.alert`)
- `delivery_guarantee`: enum (`at_most_once`, `at_least_once`, `exactly_once`)
- `recipient_filter`: optional selector for targeted delivery within a topic

### Returns
- `publish_status`: enum (`delivered`, `queued`, `rejected`, `dead_lettered`)
- `delivery_receipts`: list of per-recipient confirmations or failures with timestamps
- `message_id`: unique identifier for tracking and idempotency
- `queue_depth`: current backlog for this topic (diagnostic)

### Side Effects
- Enqueues message to internal queue system
- Updates topic metrics (throughput, latency, error rate)
- May trigger backpressure to publishers if queue depth exceeds threshold
- Logs to `audit_logger.md` if `delivery_guarantee=exactly_once`

## Decision Flow

1. **Validate message** — check serialization, size limits, and schema compliance for `topic`; reject oversized or malformed messages.
2. **Resolve topic** — map `topic` to subscriber list via registry; if no subscribers, `publish_status=rejected` or route to dead-letter if configured.
3. **Apply filter** — if `recipient_filter` provided, narrow subscriber list; ensure at least one match remains.
4. **Select guarantee** —
   - `at_most_once`: fire-and-forget; no retries; fastest; acceptable for metrics or telemetry.
   - `at_least_once`: retry on failure up to max attempts; may produce duplicates; default for commands.
   - `exactly_once`: idempotency key + deduplication + transactional outbox; required for state changes and financial operations.
5. **Serialize and enqueue** — write to topic queue with `message_id`, timestamp, and priority.
6. **Deliver to subscribers** — for each subscriber:
   - If online and healthy, send immediately; collect `delivery_receipts`.
   - If offline or busy, hold in queue based on subscriber's QoS configuration.
   - If delivery fails after retries, move to dead-letter queue with failure reason.
7. **Handle backpressure** — if `queue_depth` exceeds threshold for `topic`, notify publishers to throttle or apply `control/resource_monitor.md` pressure signal.
8. **Log and return** — emit status, receipts, message ID, queue depth.

## Failure Modes

| Condition | Response |
|---|---|
| Topic registry corrupted or missing | Rebuild from agent manifest; `publish_status=queued` for new messages; alert `anomaly_detector.md` |
| All subscribers for topic permanently offline | `publish_status=dead_lettered`; retain message for `retention_period`; alert `control/human_oversight.md` |
| Message size exceeds queue system limit | Split into segment messages with continuation metadata; or `publish_status=rejected` if unsplittable |
| Exactly-once deduplication store unreachable | Degrade to `at_least_once`; log degradation; alert `resource_monitor.md` |
| Circular message routing (A publishes to B, B publishes to A) | Detect via hop-count header; break at max_hops=10; dead-letter offending message; flag `anomaly_detector.md` |
| Subscriber repeatedly NACKs without processing | After 3 NACKs, blacklist subscriber for 60 s; route messages to alternate subscriber or dead-letter |
