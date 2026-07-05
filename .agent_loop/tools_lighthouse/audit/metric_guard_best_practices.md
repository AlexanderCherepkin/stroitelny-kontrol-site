# Best Practices Metric Guard

## Role
Validates the Lighthouse Best Practices category against the 100% hard gate. Translates failed audits into security and reliability corrections: HTTPS links, CSP, console errors, deprecated APIs, and correct `rel` attributes.

## Contract

### Receives
- `failure_summary`: from `tools_lighthouse/audit/report_parser.md`
- `category_scores`: from `tools_lighthouse/audit/audit_runner.md`
- `page_source`: optional path to generated source

### Returns
- `score`: float 0–1 for the Best Practices category
- `passed`: boolean — `score == 1.0` and no failed audits
- `corrections`: list of `{file?, selector?, issue, required_change, priority}`

### Side effects
- Logs verdict to `safety-control/mutual_check/audit_logger.md`

## Decision Flow

1. **Extract best-practices score** — read `category_scores.best_practices` or `best-practices`; if missing, default to 0.
2. **Early exit** — if `score == 1.0`, return `passed=true`.
3. **Map audits to corrections** — for each failed best-practices audit:
   - `external-anchors-use-rel-noopener` / `geolocation-on-start` / `no-document-write` → add `rel="noopener noreferrer"` to external links
   - `errors-in-console` → fix JS runtime errors; add error boundaries; avoid referencing undefined globals
   - `csp-xss` → add or tighten Content-Security-Policy headers/meta tag
   - `password-inputs-can-be-pasted-into` → ensure paste is not blocked on password fields
   - `notification-on-start` / `deprecated-apis` → remove deprecated calls and permission prompts on load
   - `image-aspect-ratio` → ensure explicit width/height on images
4. **Prioritize** — security issues first (`rel`, CSP), then console errors, then deprecated API usage.
5. **Return** — emit score, passed flag, corrections list.

## Failure Modes

| Condition | Response |
|---|---|
| Best-practices score missing | `passed=false`; corrections include generic security checklist |
| External link policy conflicts with design | Prefer `rel="noopener noreferrer"` unless explicit business requirement says otherwise |
| CSP cannot be set at build time | Provide meta-tag fallback; log limitation |
