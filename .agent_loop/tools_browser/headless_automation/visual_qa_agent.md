# Visual QA Agent

## Role
Validates a generated Next.js landing page against its Figma reference by taking Playwright screenshots and running DOM assertions, then produces a structured discrepancy report for the self-correction loop.

## Contract

### Receives
- `page_url`: URL of the generated landing page (`http://localhost:3000`, `file://...`, or staged path).
- `reference_path`: optional path to a Figma reference screenshot or exported frame image.
- `expected_nodes`: optional list of DOM assertions derived from the Tailwind AST — each entry `{selector, min_count, text?, exact_text?}`.
- `viewport`: dict `width`/`height` (default `{"width": 1280, "height": 720}`).
- `session_handle`: optional handle from `session_manager.md`; if absent, a fresh ephemeral session is created.
- `output_dir`: directory for screenshots and report (default `<workspace>/.tmp/browser/visual_qa/`).

### Returns
- `status`: enum (`passed`, `failed`, `degraded`, `blocked`).
- `screenshot_path`: absolute path to the captured page screenshot.
- `reference_screenshot_path`: absolute path to the reference screenshot if provided.
- `diff_score`: float 0.0–1.0, where 0.0 means identical and 1.0 means completely different; null if no reference.
- `dom_assertions`: list of `{selector, expected, actual, passed}`.
- `discrepancies`: list of human-readable findings.
- `metrics`: `{load_time_ms, viewport_width, viewport_height, screenshot_width, screenshot_height}`.

### Side effects
- Writes screenshot PNG to `output_dir`.
- Writes JSON report to `output_dir/report.json`.
- Invokes `safety-control/data_leak_preventer.md` before returning paths.
- Logs capture and comparison results to `audit_logger.md`.

## Decision Flow

1. **Resolve session** — use `session_handle` or create a fresh Playwright browser context via `session_manager.md`.
2. **Validate URLs/paths** — ensure `page_url` points to an allowed local/allow-listed destination via `control/network_guard.md`; reject `file://` paths outside the workspace.
3. **Navigate** — load `page_url` through `navigation_engine.md` and wait for `networkidle`.
4. **Capture screenshot** — call `screenshot_agent.md` for a full-page PNG and record dimensions.
5. **Run DOM assertions** — for each `expected_nodes` entry, query `document.querySelectorAll(selector)`, compare counts and optional text, record pass/fail.
6. **Compare reference** — if `reference_path` exists, compute a pixel diff score against the captured screenshot using a perceptual hash or structural similarity metric.
7. **Collect metrics** — load time, viewport, screenshot dimensions.
8. **Write report** — save JSON report to `output_dir/report.json`.
9. **Return** — emit status, paths, scores, assertions, discrepancies, and metrics.

## Failure Modes

| Condition | Response |
|---|---|
| Playwright not installed | `status=blocked`; log install hint; route fallback to `tools_web/web_request/request_builder.md` |
| `page_url` disallowed by network guard | `status=blocked`; route to `control/network_guard.md` |
| Navigation timeout or crash | `status=degraded`; return partial metrics and any available screenshot |
| Reference image dimensions differ | Normalize to common size before diff or record `discrepancy` and skip score |
| DOM assertion selector fails | Mark assertion failed, add to `discrepancies`, continue remaining checks |
| Sensitive pixels detected | Redact or mask via `data_leak_preventer.md`; if unblockable, `status=blocked` |
| Screenshot write outside workspace | `status=blocked`; route to `control/file_system_guard.md` |
