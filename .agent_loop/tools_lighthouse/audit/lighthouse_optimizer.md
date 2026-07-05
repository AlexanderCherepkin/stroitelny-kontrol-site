# Lighthouse Optimizer

## Role
Cross-cutting strategist for the Lighthouse audit pipeline. Selects the cheapest, most deterministic configuration: which form factors to audit, whether to run mobile and desktop in parallel, how to compress logs, and when to reuse a previous browser session.

## Contract
- **Receives**: `{ request: { page_url, workspace_root, form_factors, categories }, constraints: { time_budget_ms, token_budget, disk_quota_mb }, history: { previous_session_id?, previous_report_path? } }`
- **Returns**: `{ plan: { pipeline: [agent_name], params: {form_factors, categories, reuse_session, parallel, compression_level} }, log_policy: {retain_all, archive_after_days, max_size_mb}, estimated_cost: {time_ms, memory_mb, tokens} }`
- **Side effects**: none (planning only — execution is upstream)

## Decision Flow

1. **Analyze request shape**
   - Figma/Next.js landing page → audit both mobile and desktop, prioritize mobile (Lighthouse weights mobile higher for search ranking)
   - Internal dashboard → audit desktop only unless mobile is required
   - Single component story → skip full Lighthouse, use targeted subset
2. **Select form factors**
   - Default: `['mobile']` for fast iteration; add `['desktop']` after first pass if mobile reaches 100%
   - If user explicitly asks for both: run mobile first, then desktop sequentially to avoid port collisions
3. **Select strategy**
   - `reuse_session=true` if `previous_session_id` exists and browser is still healthy
   - `parallel=false` for local dev servers to avoid race conditions on the same port
4. **Configure pipeline**
   - Always include `session_manager.md` + `navigation_engine.md` + `audit_runner.md` + `report_parser.md`
   - Always include the four `metric_guard_*.md` agents
   - Always include `correction_prompt_builder.md` + `loop_terminator.md`
   - Skip `report_parser.md` if raw report is known small; keep it for safety
5. **Log policy**
   - `retain_all=true` — failed iteration logs are kept for prompt/skill training
   - `archive_after_days=30`
   - `max_size_mb=500` — when exceeded, oldest logs gzip into `.logs/lighthouse/archive/`
6. **Estimate cost**
   - Time: 1× browser launch (~2 s) + N navigation/audit cycles (~15 s each)
   - Memory: peak browser allocation (~300 MB per context)
   - Tokens: correction prompt size after `report_parser.md` filters failures
8. **Convergence budget** — default `lighthouse_max_iterations=8`; reduce to 5 only if caller explicitly requests speed over perfection.
9. **Validate against constraints** — if estimated time exceeds budget, drop desktop audit or reduce categories; if disk quota exceeded, lower compression level or shorten retention.

## Failure Modes

| Condition | Response |
|---|---|
| Both form factors requested but budget too low | Default to mobile only; flag trade-off |
| Disk quota exceeded | Reduce `archive_after_days` to 7 and raise compression |
| No previous report to compare | Plan as first-run full audit |
| Playwright unavailable | Suggest `tools_web/web_request` static smoke test fallback |
