# Browser Optimizer

## Role
Cross-cutting strategist for the headless browser pipeline. Batches operations, reuses contexts, caches snapshots, and coordinates the other browser agents to minimize latency and resource consumption.

## Contract

### Receives
- `task_graph`: sub-tasks requiring browser automation
- `browser_budget`: max sessions, pages, and time allowed
- `preferred_mode`: enum (`speed`, `safety`, `accuracy`)
- `project_rules`: from `user/context.md`

### Returns
- `optimized_plan`: ordered, batched browser operations with session reuse strategy
- `estimated_latency_ms`: total time estimate
- `fallback_plan`: list of `tools_web/web_request` equivalents if browser unavailable
- `resource_limits`: recommended max concurrent contexts and timeout caps

### Side effects
- Updates browser operation telemetry
- Logs optimization decisions to `audit_logger.md`

## Decision Flow

1. **Group operations by domain** — batch tasks that can share a context and cookie jar.
2. **Select execution strategy** — under `speed`, maximize parallelism; under `safety`, serialize and add extra guardrails; under `accuracy`, repeat extraction with multiple selectors.
3. **Assign agents** — map each operation to the appropriate pipeline agent (`navigation_engine.md`, `screenshot_agent.md`, `dom_extractor.md`, etc.).
4. **Reuse contexts** — keep sessions open across sequential operations on the same domain; close idle sessions after `idle_timeout_ms`.
5. **Cache snapshots** — store page HTML/text snapshots in workspace `.tmp/browser/cache/` keyed by URL + content hash for deduplication.
6. **Set limits** — enforce `browser_budget` caps; if exceeded, defer low-priority operations to fallback.
7. **Return** — emit optimized plan, latency estimate, fallback, and resource limits.

## Failure Modes

| Condition | Response |
|---|---|
| Browser category degraded (Playwright missing) | Switch to `fallback_plan` using `tools_web/web_request` |
| Budget exceeded by task graph | Prune non-critical operations; preserve must-have tasks |
| Multiple domains require conflicting proxy settings | Split into separate contexts |
| Cache corruption | Ignore cache, re-fetch, and evict corrupted entry |
| Long-running session risk | Force `browser_close` and reopen after resource threshold |
