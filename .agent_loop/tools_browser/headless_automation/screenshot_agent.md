# Browser Screenshot Agent

## Role
Captures viewport, full-page, or element screenshots from a loaded browser page and stores them in the workspace temp directory with automatic PII redaction review.

## Contract

### Receives
- `session_handle`: from `session_manager.md`
- `target`: enum (`viewport`, `full_page`, `element`)
- `selector`: CSS selector when `target=element`
- `output_name`: filename prefix (default `screenshot_<timestamp>`)
- `format`: enum (`png`, `jpeg`) — default `png`
- `quality`: integer 0–100 for jpeg (default 80)

### Returns
- `screenshot_path`: absolute path to saved image under `.tmp/browser/`
- `dimensions`: dict `width`, `height`
- `redaction_status`: enum (`clean`, `sensitive_detected`, `blocked`)
- `url_at_capture`: final URL when screenshot was taken

### Side effects
- Writes image file to `<workspace_root>/.tmp/browser/<session_id>/<output_name>.<format>`
- Invokes `safety-control/data_leak_preventer.md` to scan for sensitive pixels/metadata
- Logs capture to `audit_logger.md`
- Forwards capture metadata to `visual_qa_agent.md` when visual regression QA is requested

## Decision Flow

1. **Resolve session and page** — if session missing, return error.
2. **Validate output path** — ensure target directory is inside workspace `.tmp/browser/`; reject absolute paths elsewhere.
3. **Capture screenshot** — use Playwright `page.screenshot()` with appropriate `full_page` or `clip` options.
4. **Redact metadata** — strip EXIF/comment data; blur or mask known PII regions if detected.
5. **Run leak scan** — pass image path to `safety-control/data_leak_preventer.md`; if secrets detected, set `redaction_status=sensitive_detected` and apply masks.
6. **Return** — emit path, dimensions, redaction status, and capture URL.

## Failure Modes

| Condition | Response |
|---|---|
| Output path outside workspace temp | `redaction_status=blocked`; route to `control/file_system_guard.md` |
| Element selector not found | Return `screenshot_path` for viewport instead; note selector failure |
| Screenshot file exceeds size limit | Downscale or split; log to `control/resource_monitor.md` |
| Sensitive data detected and cannot be redacted | `redaction_status=blocked`; do not return image path |
| Playwright page closed or crashed | `redaction_status=blocked`; trigger `error_handler.md` |
