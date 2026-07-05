# Lighthouse Navigation Engine

## Role
Loads the target page inside a Playwright context and stabilizes it before the Lighthouse audit runs. Blocks disallowed URLs, waits for network idle, and disables animations/fonts-variability to make audits deterministic.

## Contract

### Receives
- `page_url`: URL of the generated site (`http://localhost:3000` or staged path)
- `session_handle`: from `tools_lighthouse/audit/session_manager.md`
- `form_factor`: enum (`mobile`, `desktop`)
- `wait_for_network_idle`: boolean (default true)
- `extra_headers`: optional dict of HTTP headers

### Returns
- `page_handle`: opaque handle bound to the loaded page
- `load_time_ms`: integer — time to `load` event
- `navigation_status`: enum (`ready`, `blocked`, `timeout`, `error`)
- `error`: human-readable error if navigation failed

### Side effects
- Navigates the Playwright page
- Writes navigation log to `<workspace_root>/.tmp/lighthouse/<session_id>/navigation.log`
- Logs to `safety-control/mutual_check/audit_logger.md`

## Decision Flow

1. **Validate URL** — ensure `page_url` points to an allowed local/allow-listed destination via `control/network_guard.md`; reject `file://` paths outside the workspace.
2. **Resolve session** — retrieve the Playwright context/page associated with `session_handle`; if missing, request a fresh session from `session_manager.md`.
3. **Apply form factor** — for `mobile`, set viewport to 360×640 with DPR 2.625; for `desktop`, use 1280×720 with DPR 1.
4. **Disable animations** — inject CSS `*, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; }` to remove animation jitter from metrics.
5. **Navigate** — load `page_url` with `waitUntil="networkidle"` if `wait_for_network_idle=true`, otherwise `domcontentloaded`.
6. **Measure load time** — record time from navigation start to `load` event.
7. **Check for errors** — collect `pageerror` and `console` error events during navigation; if critical, set `navigation_status=error`.
8. **Return** — emit `page_handle`, `load_time_ms`, `navigation_status`.

## Failure Modes

| Condition | Response |
|---|---|
| `page_url` disallowed by network guard | `navigation_status=blocked`; route to `control/network_guard.md` |
| Navigation timeout | `navigation_status=timeout`; emit partial metrics and error |
| Page crashes after load | `navigation_status=error`; capture stack trace and log to `audit_logger.md` |
| `session_handle` invalid | Request new session from `session_manager.md`; if still invalid, `navigation_status=error` |
| Console errors exceed threshold (>5) | Log warning; continue audit but flag `navigation_status=degraded` |
