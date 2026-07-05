# Headroom Compressor

## Role

Observation-phase agent that compresses large raw artifacts (tool outputs, runtime logs, RAG chunks, file contents) before they are passed to the next ReAct phase or stored in memory. Uses the optional Headroom SDK with graceful fallback to passthrough.

## Contract

### Receives

- `raw_content`: string or list of chat messages to compress.
- `content_type`: enum (`tool_output`, `log`, `file`, `rag`, `messages`) — guides routing.
- `model`: string | None — target LLM for token counting (default from `HEADROOM_MODEL` or runtime config).
- `target_ratio`: float | None — optional keep-ratio for aggressive/conservative compression.
- `force`: boolean — compress even if below default threshold (default `false`).
- `headroom_enabled`: boolean | None — override; falls back to `HEADROOM_ENABLED` env, then `true`.

### Returns

- `compressed_content`: compressed text or messages.
- `hash`: string — CCR hash for later retrieval (empty if unavailable).
- `original_tokens`: integer.
- `compressed_tokens`: integer.
- `tokens_saved`: integer.
- `savings_percent`: float.
- `retrieval_hint`: string — instruction for how to recover full content.
- `available`: boolean — whether Headroom was actually used.

### Side effects

- Stores original content in local Headroom CCR store (if available).
- Logs compression event to `audit_logger.md`.

## Decision Flow

1. **Check availability** — use `runtime/engine/headroom_client.py` to determine if Headroom is installed and enabled.
2. **Short-circuit if disabled** — if unavailable and `force=false`, return passthrough result with `available=false`.
3. **Measure size** — estimate tokens in `raw_content`; if below `min_tokens_to_compress` and `force=false`, return passthrough.
4. **Route by `content_type`**:
   - `messages` → call `headroom_client.compress_messages`;
   - other types → wrap as tool message and call `headroom_client.compress_text`.
5. **Store original** — capture returned hash; if compression fails, keep original and report error.
6. **Return** — emit compressed payload plus metrics and retrieval hint.

## Failure Modes

| Condition | Response |
|---|---|
| `headroom-ai` not installed | Passthrough with `available=false`; no hash; log once per session |
| Compression raises exception | Return original content, `available=true`, `error` field; alert `mutual_check/anomaly_detector.md` |
| Compressed result longer than original | Return original; log negative-compression warning |
| `raw_content` empty or whitespace | Return empty result with zero metrics |
| Safety-critical content flagged | Skip compression and return original; log override |
