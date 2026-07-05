# Headroom Injector

## Role

Planning agent that decides where Headroom context compression should be applied in the ReAct tool plan. Identifies heavy context segments (large tool outputs, logs, RAG chunks, multi-agent handoffs) and inserts compression/retrieval steps without changing the underlying agent contracts.

## Contract

### Receives

- `task_graph`: from `task_decomposition.md` — ordered sub-tasks and parallel groups.
- `available_mcp_categories`: list of registered MCP category names (from `mcp_servers/gateway.py`).
- `headroom_enabled`: boolean | None — explicit override; falls back to `HEADROOM_ENABLED` env, then `true`.
- `token_budget`: integer — remaining context-window budget for the session.
- `execution_policy`: enum (`speed_priority`, `accuracy_priority`, `cost_priority`, `safety_priority`).

### Returns

- `compression_plan`: list of `{ phase, trigger, threshold_tokens, tool, fallback, notes }` entries describing where to compress or retrieve.
- `headroom_selected`: boolean — true if any Headroom step was planned.
- `estimated_tokens_saved`: integer — rough upper-bound savings estimate.

### Side effects

- Logs compression plan to `audit_logger.md`.

## Decision Flow

1. **Check availability** — if `headroom` is not in `available_mcp_categories`, or `headroom_enabled` resolves to `false`, return empty `compression_plan` and `headroom_selected=false`.
2. **Scan `task_graph` for heavy context producers** — flag phases whose outputs are typically large:
   - `tools_runcom/run_command` (build logs, test output, CLI dumps);
   - `tools_search/search_code` (many results, snippets, diffs);
   - `tools_read/read_file` on files expected to exceed threshold;
   - `tools_web/web_request` (RAG chunks, large responses);
   - `tools_browser/headless_automation` (DOM dumps, screenshots metadata);
   - multi-agent handoffs between `tooll_subagents/` phases.
3. **Apply thresholds** — only flag outputs when expected tokens exceed `min(500, token_budget // 10)`; if `execution_policy=safety_priority` or `accuracy_priority`, raise threshold to avoid losing detail.
4. **Choose strategy per flagged phase**:
   - Single large output → `headroom_compress` before passing to next agent;
   - Repeated reads of the same file → cache marker + `headroom_retrieve` on demand;
   - Shared state between sub-agents → `runtime/engine/headroom_client.py` `SharedContext`;
   - End-of-session summary → `headroom_stats`.
5. **Insert into plan** — add `headroom_compressor.md` observation step after each flagged producer and `headroom_retriever.md` before any consumer that may need full detail.
6. **Estimate savings** — sum `expected_tokens - compressed_tokens` using historical 60–70 % reduction; cap by `token_budget`.
7. **Return** — emit `compression_plan`, `headroom_selected`, `estimated_tokens_saved`.

## Failure Modes

| Condition | Response |
|---|---|
| `headroom` MCP category unavailable | Empty plan; `headroom_selected=false`; log degraded state |
| `headroom_enabled=false` | Empty plan; no logging overhead |
| `token_budget` too small for compression overhead | Raise threshold or skip compression; log reason |
| Ambiguous output size | Use conservative estimate and plan a conditional compression (compress only if size exceeds threshold at runtime) |
| `execution_policy=safety_priority` | Avoid compressing safety-relevant outputs; prefer passthrough |
