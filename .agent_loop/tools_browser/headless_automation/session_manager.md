# Browser Session Manager

## Role
Lifecycle manager for Playwright browser contexts. Creates isolated, ephemeral browser profiles, attaches pages to sessions, and guarantees cleanup on success, failure, or timeout.

## Contract

### Receives
- `session_id`: unique identifier for the browser session
- `headless`: boolean — run browser without GUI (default true)
- `viewport`: dict with `width`, `height` (default 1280x720)
- `user_agent`: optional override string
- `proxy`: optional proxy configuration dict
- `workspace_root`: path to project root for temporary storage

### Returns
- `session_handle`: opaque handle to pass to other browser tools
- `browser_version`: detected browser version string or null
- `context_isolation`: boolean — confirms incognito/ephemeral context
- `status`: enum (`ready`, `degraded`, `failed`)
- `error`: human-readable error if status is failed

### Side effects
- Spawns Playwright browser process
- Creates temporary profile directory under `<workspace_root>/.tmp/browser/<session_id>/`
- Logs session creation to `safety-control/mutual_check/audit_logger.md`

## Decision Flow

1. **Check Playwright availability** — if `playwright` is not installed, return `status=failed` with installation hint; do not auto-install.
2. **Validate workspace** — ensure `<workspace_root>/.tmp/browser/` exists and is writable; create if missing.
3. **Build launch options** — set `headless`, `viewport`, `args=[--no-sandbox, --disable-dev-shm-usage]` for CI environments; apply `user_agent` and `proxy` if provided.
4. **Launch context** — create a `BrowserContext` in incognito mode with ephemeral storage (cookies, localStorage cleared on close).
5. **Register session** — store context, page, and metadata in the runtime session registry keyed by `session_id`.
6. **Return handle** — emit `session_handle`, `browser_version`, `context_isolation=true`, `status=ready`.
7. **Schedule cleanup** — register an atexit/finally hook to call `browser_close` if the caller forgets.

## Failure Modes

| Condition | Response |
|---|---|
| Playwright or browser binary missing | `status=failed`; suggest `pip install playwright && playwright install`; route fallback to `tools_web/web_request/request_builder.md` |
| Workspace temp directory not writable | `status=failed`; log to `audit_logger.md`; escalate to `control/file_system_guard.md` |
| Browser process crashes on launch | `status=failed`; retry once with `--disable-gpu`; if still failing, return error |
| Proxy configuration invalid | `status=degraded`; ignore proxy and continue with direct connection |
| Session ID collision | Reuse existing session if active; otherwise generate new handle and log warning |
