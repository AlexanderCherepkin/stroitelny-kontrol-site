# API Gateway

## Role
External interface agent that handles all inbound and outbound API traffic for the Agentic Loop. Manages authentication, rate limiting, protocol translation, request/response marshaling, and error normalization. Serves as the single entry point for external clients and the exit point for outbound tool calls.

## Contract

### Receives
- `api_request`: inbound HTTP/gRPC/WebSocket request or outbound third-party API call descriptor
- `direction`: enum (`inbound`, `outbound`)
- `protocol`: enum (`http_1`, `http_2`, `grpc`, `websocket`, `webhook`)
- `auth_context`: credentials, tokens, or session identifiers

### Returns
- `api_response`: normalized response payload with status code, headers, and body
- `gateway_status`: enum (`processed`, `rate_limited`, `unauthenticated`, `forbidden`, `upstream_error`, `timeout`)
- `latency_ms`: round-trip time
- `audit_reference`: traceable ID for this API transaction

### Side Effects
- Consumes rate-limit quota via `mutual_check/quota_manager.md`
- Validates credentials against identity provider
- Logs transaction to `audit_logger.md`
- May trigger `control/network_guard.md` for outbound calls

## Decision Flow

1. **Parse request** — decode `api_request` according to `protocol`; extract path, headers, body, and metadata.
2. **Authenticate** — validate `auth_context` against identity provider; if invalid, `gateway_status=unauthenticated`.
3. **Authorize** — check permissions for authenticated identity to perform this operation on this resource; if denied, `gateway_status=forbidden`.
4. **Rate limit** — consult `mutual_check/quota_manager.md` for per-identity and global rate limits; if exceeded, `gateway_status=rate_limited` with retry-after header.
5. **Route internally or externally** —
   - `inbound`: map to `main_loop.md` or `router.md` based on path and payload type.
   - `outbound`: apply `control/network_guard.md` destination check, then forward to third-party API.
6. **Translate protocol** — normalize inbound request to internal message format; convert internal response to outbound protocol format.
7. **Marshal payload** — validate against schema (JSON Schema, protobuf); reject malformed payloads with `gateway_status=upstream_error` and detailed error.
8. **Execute** — forward to internal handler or external endpoint; enforce timeout based on operation SLA.
9. **Handle error** — translate upstream errors into standardized gateway response format; include `audit_reference` for debugging.
10. **Log and return** — emit response, status, latency, audit reference.

## Failure Modes

| Condition | Response |
|---|---|
| Identity provider unreachable | `gateway_status=unauthenticated` for new requests; accept cached sessions with reduced TTL; alert `network_guard.md` |
| Protocol parsing fails (malformed HTTP/2, invalid protobuf) | `gateway_status=upstream_error`, return 400 with parse error details; do not retry malformed |
| Outbound TLS certificate validation fails | `gateway_status=upstream_error`, block request; log certificate fingerprint; alert `network_guard.md` |
| Rate limiter state inconsistency (count negative) | Reset counter to zero; `gateway_status=rate_limited` conservatively; flag `anomaly_detector.md` |
| Upstream API returns 5xx with retry-after | Respect retry-after; if absent, use exponential backoff up to 3 retries; if still failing, `gateway_status=upstream_error` |
| WebSocket connection drops mid-stream | Buffer incomplete messages; attempt reconnect once; if fails, `gateway_status=timeout` with partial payload |
