# Performance Metric Guard

## Role
Validates the Lighthouse Performance category against the 100% hard gate. Translates failed performance audits into concrete front-end corrections: image loading, layout shifts, render-blocking resources, and JavaScript weight.

## Contract

### Receives
- `failure_summary`: from `tools_lighthouse/audit/report_parser.md`
- `category_scores`: from `tools_lighthouse/audit/audit_runner.md`
- `page_source`: optional path to the generated page/component source for targeted fixes

### Returns
- `score`: float 0–1 for the Performance category
- `passed`: boolean — `score == 1.0` and no failed audits
- `corrections`: list of `{file?, selector?, issue, required_change, priority}`

### Side effects
- Logs verdict to `safety-control/mutual_check/audit_logger.md`

## Decision Flow

1. **Extract performance score** — read `category_scores.performance`; if missing, default to 0.
2. **Early exit** — if `score == 1.0` and no failed audits, return `passed=true` with empty corrections.
3. **Map audits to corrections** — for each failed performance audit:
   - `largest-contentful-paint` / `lcp-lazy-loaded` → add `fetchpriority="high"`, remove `loading="lazy"` from hero media
   - `cumulative-layout-shift` → enforce `aspect-ratio`, explicit `width`/`height`, reserved space for dynamic content
   - `render-blocking-resources` → inline critical CSS or defer non-critical styles/scripts
   - `unused-javascript`, `unused-css-rules` → remove dead imports or split bundles
   - `total-blocking-time`, `max-potential-fid` → reduce main-thread JS, split long tasks, use `requestIdleCallback`
   - `modern-image-formats`, `efficiently-encode-images` → prefer WebP/AVIF via `ResponsivePicture`
4. **Prioritize** — rank corrections by Lighthouse weight and estimated fix impact.
5. **Return** — emit score, passed flag, corrections list.

## Failure Modes

| Condition | Response |
|---|---|
| Performance score missing | `passed=false`; corrections include generic LCP/CLS/INP guidance |
| Score stuck below 1.0 after 8 iterations | Return best-effort corrections with `priority=low`; log to `audit_logger.md` |
| Correction conflicts with design constraints | Note constraint conflict; escalate trade-off to `plan_adjustment.md` |
