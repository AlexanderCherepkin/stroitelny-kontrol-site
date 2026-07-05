# Browser Navigation Engine

## Role
URL loader that waits for dynamic content, handles redirects and frames, and produces a stable page snapshot for downstream extraction or screenshot agents.

## Contract

### Receives
- `session_handle`: from `session_manager.md`
- `url`: target URL (must be HTTP/HTTPS)
- `wait_until`: enum (`load`, `domcontentloaded`, `networkidle`, `commit`) — default `networkidle`
- `timeout_ms`: max navigation time (default 30000)
- `allowed_domains`: list of permitted domains from `control/network_guard.md`

### Returns
- `navigation_status`: enum (`success`, `timeout`, `blocked`, `error`)
- `final_url`: URL after redirects
- `page_title`: document title
- `load_time_ms`: elapsed navigation time
- `frames`: list of frame descriptors (id, src, name)

### Side effects
- Mutates the active page in the browser session
- Writes navigation event to `audit_logger.md`
- May trigger `control/network_guard.md` if URL is not allowed

## Decision Flow

1. **Resolve session** — look up `session_handle`; if missing, return `navigation_status=error`.
2. **Validate URL** — ensure scheme is `http` or `https`; reject `file://`, `javascript:`, `data:` URLs.
3. **Domain allow-list check** — if `allowed_domains` provided and host not in list, return `navigation_status=blocked` and route to `control/network_guard.md`.
4. **Navigate** — call `page.goto(url, wait_until=wait_until, timeout=timeout_ms)`.
5. **Capture metadata** — record `final_url`, `page_title`, `load_time_ms`, and top-level frames.
6. **Handle failure** — on timeout, capture current URL and partial DOM; on error, classify via `error_handler.md`.
7. **Return** — emit navigation status and metadata.

## Failure Modes

| Condition | Response |
|---|---|
| Session handle invalid | `navigation_status=error`; request new session via `session_manager.md` |
| URL scheme disallowed | `navigation_status=blocked`; log to `safety-control/threat_detector.md` |
| Domain not in allow-list | `navigation_status=blocked`; route to `control/network_guard.md` |
| Navigation timeout | `navigation_status=timeout`; return partial snapshot if available |
| Infinite redirect loop | Abort after 10 redirects; `navigation_status=error` |
| Page triggers download dialog | Cancel download; `navigation_status=success` if main frame loaded |
