# Accessibility Metric Guard

## Role
Validates the Lighthouse Accessibility category against the 100% hard gate. Converts failed a11y audits into specific DOM corrections: touch targets, ARIA labels, contrast, heading order, and keyboard semantics.

## Contract

### Receives
- `failure_summary`: from `tools_lighthouse/audit/report_parser.md`
- `category_scores`: from `tools_lighthouse/audit/audit_runner.md`
- `page_source`: optional path to generated source

### Returns
- `score`: float 0–1 for the Accessibility category
- `passed`: boolean — `score == 1.0` and no failed audits
- `corrections`: list of `{file?, selector?, issue, required_change, priority}`

### Side effects
- Logs verdict to `safety-control/mutual_check/audit_logger.md`

## Decision Flow

1. **Extract accessibility score** — read `category_scores.accessibility`; if missing, default to 0.
2. **Early exit** — if `score == 1.0`, return `passed=true`.
3. **Map audits to corrections** — for each failed a11y audit:
   - `tap-targets` / `target-size` → ensure clickables are ≥48×48 px on mobile via `TouchSafeElement`
   - `aria-*` rules (`aria-required-attr`, `aria-roles`, `aria-valid-attr-values`) → add correct ARIA attributes
   - `button-name`, `link-name`, `image-alt` → enforce `alt`/`aria-label`; route image fixes through `ResponsivePicture`
   - `color-contrast` → bump contrast ratio to ≥4.5:1 (≥3:1 for large text)
   - `heading-order` → guarantee exactly one `h1`, no skipped levels
   - `html-has-lang`, `document-title` → set `lang` and `title`
4. **Prioritize** — critical first (touch targets, contrast), then semantic (headings, ARIA), then polish.
5. **Return** — emit score, passed flag, corrections list.

## Failure Modes

| Condition | Response |
|---|---|
| Accessibility score missing | `passed=false`; corrections include generic a11y checklist |
| Touch-target fixes conflict with Figma exact sizing | Flag trade-off; prefer 48×48 minimum unless human override present |
| Contrast cannot be fixed within palette | Suggest token change; if blocked, escalate to `assistance_request.md` |
