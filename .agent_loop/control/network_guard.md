# Network Guard

## Role
Runtime enforcement agent that controls outbound and inbound network connectivity. Restricts destinations, protocols, bandwidth, and connection durations to prevent data exfiltration, command-and-control communication, and unauthorized external access.

## Contract

### Receives
- `connection_request`: descriptor containing protocol, destination host/port, payload size estimate
- `identity`: agent or user initiating connection
- `purpose_tag`: enum (`api_call`, `telemetry`, `update`, `user_content`, `diagnostic`)
- `expected_duration`: estimated session length or one-shot flag

### Returns
- `connection_verdict`: enum (`allow`, `deny`, `proxy`, `rate_limited`, `time_limited`)
- `allowed_endpoints`: list of specific hosts/ports permitted for this operation
- `bandwidth_cap`: bytes per second or null
- `session_timeout`: seconds or null
- `block_reason`: string or null

### Side Effects
- Logs connection to `audit_logger.md`
- Installs temporary firewall rule if `allow` or `proxy`
- Updates per-identity bandwidth counter

## Decision Flow

1. **Resolve destination** — DNS lookup if needed; check against known-malicious IP/host lists.
2. **Match against allow-list** — verify destination in identity-specific or global allow-list.
3. **Match against deny-list** — block if destination matches known bad actors, competitor IPs, or non-essential external services.
4. **Evaluate purpose** — `api_call` and `telemetry` typically allowed to approved endpoints; `user_content` may require additional sanitization.
5. **Check bandwidth quota** — if identity or system near cap, downgrade to `rate_limited` with reduced `bandwidth_cap`.
6. **Check time limits** — if `expected_duration` exceeds policy, apply `session_timeout`.
7. **Determine verdict** — `allow` if clean and within quota; `proxy` if destination requires inspection; `rate_limited` if quota pressure; `time_limited` if duration capped; `deny` if any block rule triggered.
8. **Apply and log** — install rule, emit verdict, log.

## Failure Modes

| Condition | Response |
|---|---|
| DNS resolution returns unexpected IP | `connection_verdict=deny`, `block_reason="DNS_ANOMALY"`, flag `anomaly_detector.md` |
| Allow-list empty and no default policy | `connection_verdict=deny`, `block_reason="NO_ALLOW_RULE"` |
| Bandwidth counter corrupted | Reset counter from last known good state; apply conservative cap |
| Firewall rule installation fails | `connection_verdict=deny`, escalate to `resource_monitor.md` |
| HTTPS certificate pinning mismatch | `connection_verdict=deny`, `block_reason="CERT_MISMATCH"` |
| Figma asset download batch not pre-approved by `tooll_subagents/planning/asset_agent.md` | `connection_verdict=rate_limited`; require plan token before allowing `api.figma.com/images` bulk requests |
| External image search/download not pre-approved by `tooll_subagents/planning/image_enrichment_agent.md` | `connection_verdict=rate_limited`; require plan token before allowing provider image API / download hosts |
