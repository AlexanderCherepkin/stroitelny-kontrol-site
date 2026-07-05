# Headroom Retriever

## Role

Observation-phase agent that restores original uncompressed content by CCR hash when another agent or the LLM needs details that were previously compressed by `headroom_compressor.md`.

## Contract

### Receives

- `hash`: string — CCR hash returned by a prior `headroom_compress` call.
- `source_hint`: enum (`auto`, `local`, `proxy`) — preferred retrieval source (default `auto`).
- `headroom_enabled`: boolean | None — override; falls back to `HEADROOM_ENABLED` env, then `true`.

### Returns

- `original_content`: string | None — full uncompressed content if found.
- `found`: boolean.
- `source`: string — `local`, `proxy`, or `none`.
- `hash`: string — echoed for traceability.
- `error`: string | None — human-readable error if retrieval failed.
- `available`: boolean — whether Headroom was usable.

### Side effects

- Logs retrieval event to `audit_logger.md`.
- Updates Headroom session stats.

## Decision Flow

1. **Validate hash** — reject empty or malformed hashes immediately with `found=false`.
2. **Check availability** — if Headroom is disabled/unavailable, return `available=false` and advise re-reading original source.
3. **Retrieve local CCR store** — call `runtime/engine/headroom_client.py` `retrieve(hash)`.
4. **Proxy fallback** — if local miss and `source_hint` allows proxy, try `HEADROOM_PROXY_URL` `/v1/retrieve`.
5. **Return** — emit original content, source, and recovery hints if not found.

## Failure Modes

| Condition | Response |
|---|---|
| Hash empty or non-string | `found=false`, `error=invalid hash`; do not call store |
| Content expired | `found=false`, `error=content expired`; hint to re-read/re-run original source |
| Local miss and proxy unreachable | `found=false`, `error=proxy unreachable`; log to `mutual_check/anomaly_detector.md` |
| `headroom-ai` not installed | `available=false`; hint to re-read original source |
| Retrieval raises exception | Return `found=false` with error details; preserve hash |
