# Lighthouse Session Manager

## Role
Lifecycle manager for Playwright browser contexts dedicated to Lighthouse audits. Creates isolated, ephemeral profiles, pins stable Chrome flags, and guarantees cleanup after the audit regardless of success, failure, or timeout.

## Contract

### Receives
- `session_id`: unique identifier for the Lighthouse audit session
- `headless`: boolean — run browser without GUI (default true)
- `viewport`: dict with `width`, `height` (default 1280x720)
- `user_agent`: optional override string
- `workspace_root`: path to project root for temporary storage

### Returns
- `session_handle`: opaque handle to pass to `navigation_engine.md` and `audit_runner.md`
- `browser_version`: detected browser version string or null
- `context_isolation`: boolean — confirms incognito/ephemeral context
- `status`: enum (`ready`, `degraded`, `failed`)
- `error`: human-readable error if status is failed

### Side effects
- Spawns or reuses a Playwright browser process
- Creates temporary profile directory under `<workspace_root>/.tmp/lighthouse/<session_id>/`
- Logs session creation to `safety-control/mutual_check/audit_logger.md`

## Decision Flow

1. **Check Playwright availability** — if `playwright` is not installed, return `status=failed` with installation hint; do not auto-install.
2. **Validate workspace** — ensure `<workspace_root>/.tmp/lighthouse/` exists and is writable via `control/file_system_guard.md`; create if missing.
3. **Build launch options** — set `headless`, `viewport`, and Chrome stability flags `[--no-sandbox, --disable-dev-shm-usage, --disable-gpu, --disable-extensions, --disable-background-timer-throttling]` for CI environments; apply `user_agent` if provided.
4. **Launch context** — create a `BrowserContext` in incognito mode with ephemeral storage (cookies, localStorage cleared on close).
5. **Register session** — store context, page, and metadata in the runtime session registry keyed by `session_id`.
6. **Return handle** — emit `session_handle`, `browser_version`, `context_isolation=true`, `status=ready`.
7. **Schedule cleanup** — register an atexit/finally hook to close the context and delete the profile directory if the caller forgets.

## Failure Modes

| Condition | Response |
|---|---|
| Playwright or browser binary missing | `status=failed`; suggest `pip install playwright && playwright install`; route fallback to `tools_browser/headless_automation/session_manager.md` |
| Workspace temp directory not writable | `status=failed`; log to `audit_logger.md`; escalate to `control/file_system_guard.md` |
| Browser process crashes on launch | `status=failed`; retry once with `--disable-gpu`; if still failing, return error |
| Session ID collision | Reuse existing session if active; otherwise generate new handle and log warning |
