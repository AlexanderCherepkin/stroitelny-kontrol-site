# Router

## Role
Traffic-direction agent that determines which layer and which agent within the layer should handle a given request or intermediate artifact. Applies routing rules based on request type, payload schema, urgency, and system state to minimize latency and maximize correctness.

## Contract

### Receives
- `payload`: the message, command, or artifact to route
- `payload_type`: enum (`user_request`, `safety_check`, `tool_call`, `mcp_call`, `observation`, `control_signal`, `mutual_validation`, `system_alert`)
- `origin_layer`: enum (`main_loop`, `user_input`, `safety_control`, `mutual_check`, `control`, `tooll_subagents`, `tools_*`, `result`)
- `routing_policy`: enum (`direct`, `load_balanced`, `priority_queue`, `failover`)

### Returns
- `destination`: layer and agent identifier for next hop
- `route_path`: ordered list of intermediate nodes if multi-hop required
- `routing_latency_ms`: estimated time to deliver
- `fallback_destination`: secondary target if primary unavailable

### Side Effects
- Updates routing telemetry (hits, latency, error rate per destination)
- May trigger dynamic rerouting if destination degraded

## Decision Flow

1. **Classify payload** — inspect `payload_type` and schema to identify handling domain (read vs write vs safety vs validation).
2. **Select primary layer** — map `payload_type` to default layer: `user_request` → `tooll_subagents/user/`; `safety_check` → `safety-control/`; `tool_call` → `tooll_subagents/execution/`; `mcp_call` → `tooll_subagents/execution/tool_invocation.md` → `mcp_servers/gateway.py`; `observation` → `tooll_subagents/observability/`; `control_signal` → `control/`; `mutual_validation` → `mutual_check/`; `system_alert` → `control/resource_monitor.md` + `human_oversight.md`.
3. **Select agent within layer** — use capability matrix and current agent health to choose specific agent (e.g., `read` tool call → `tools_read/read_file/`).
4. **Apply routing policy** — `direct` → single hop; `load_balanced` → distribute across healthy replicas; `priority_queue` → jump queue for urgent; `failover` → route to fallback if primary fails health check.
5. **Check health** — verify destination agent or layer is responsive and not throttled by `quota_manager.md` or `resource_monitor.md`.
6. **Build route path** — if destination is `tooll_subagents/execution/tool_invocation.md`, path may be `router → dispatcher → tool_invocation → tools_*`.
7. **Select fallback** — if primary unhealthy, choose next best destination from capability matrix with fallback policy.
8. **Log and return** — emit destination, path, latency estimate, fallback.

## Failure Modes

| Condition | Response |
|---|---|
| No healthy destination for payload type | `destination=null`, route to `control/human_oversight.md` with emergency alert |
| Routing loop detected (A→B→A) | Break loop, choose next alternative; log loop to `audit_logger.md` |
| Payload schema unrecognizable | Default to `safety-control/input_sanitizer.md`; if still unparseable, `fallback_destination=human_oversight.md` |
| Routing policy produces conflicting priorities | Apply `priority_queue` override for `user_request` and `system_alert`; log conflict |
| Telemetry corruption masks agent health | Assume worst-case; route conservatively to highest-reliability agent; flag `anomaly_detector.md` |
