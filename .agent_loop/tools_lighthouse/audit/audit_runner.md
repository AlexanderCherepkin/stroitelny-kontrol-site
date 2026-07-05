# Lighthouse Audit Runner

## Role
Executes a Lighthouse audit against a Playwright-stabilized page and returns the raw JSON report for both mobile and desktop form factors.

## Contract

### Receives
- `page_handle`: from `tools_lighthouse/audit/navigation_engine.md`
- `form_factor`: enum (`mobile`, `desktop`)
- `audit_categories`: list of categories to score (`performance`, `accessibility`, `best-practices`, `seo`)
- `output_dir`: directory for raw report (default `<workspace>/.tmp/lighthouse/<session_id>/`)

### Returns
- `raw_report_path`: absolute path to the full Lighthouse JSON report
- `category_scores`: dict `{performance, accessibility, best_practices, seo}` each 0–1
- `status`: enum (`passed`, `failed`, `degraded`)
- `error`: human-readable error if the audit could not run

### Side effects
- Runs Lighthouse via the Playwright page connection (e.g., `playwright-lighthouse` flow)
- Writes raw JSON report to `output_dir/raw-<form_factor>-<timestamp>.json.gz`
- Invokes `safety-control/data_leak_preventer.md` to redact any sensitive URLs or tokens before returning paths
- Logs to `safety-control/mutual_check/audit_logger.md`

## Decision Flow

1. **Validate prerequisites** — ensure `page_handle` is valid and the page is loaded; if not, route to `navigation_engine.md` to reload.
2. **Select configuration** — build Lighthouse options:
   - `formFactor`: `mobile` or `desktop`
   - `screenEmulation`: disabled=false, mobile flag set per form factor
   - `throttling`: for mobile use 4× CPU slowdown, 150 ms RTT, 1638.4 kbps throughput; for desktop use no throttling
   - `onlyCategories`: the requested audit categories
3. **Run audit** — execute Lighthouse against the Playwright page port/CDP endpoint; capture the full JSON report.
4. **Compress and store** — gzip the raw report and save to `output_dir/raw-<form_factor>-<timestamp>.json.gz`.
5. **Extract scores** — pull `categories.*.score` for each requested category.
6. **Redact sensitive data** — pass report metadata through `safety-control/data_leak_preventer.md` before emitting paths.
7. **Return** — emit `raw_report_path`, `category_scores`, `status=passed` if scores extracted, otherwise `failed`/`degraded`.

## Failure Modes

| Condition | Response |
|---|---|
| Lighthouse module unavailable | `status=failed`; suggest dependency install; log to `audit_logger.md` |
| Playwright page disconnected | `status=failed`; attempt one reconnect via `navigation_engine.md` |
| Audit times out (>120 s) | `status=failed`; emit partial report if any; log timeout |
| All category scores null | `status=failed`; include diagnostics |
| Sensitive URL/token found in report | Redact via `data_leak_preventer.md`; if unblockable, `status=failed` |
