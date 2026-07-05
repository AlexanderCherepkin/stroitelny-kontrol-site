# SEO Metric Guard

## Role
Validates the Lighthouse SEO category against the 100% hard gate. Translates failed SEO audits into semantic HTML corrections: heading hierarchy, meta tags, canonical links, structured data, and mobile viewport.

## Contract

### Receives
- `failure_summary`: from `tools_lighthouse/audit/report_parser.md`
- `category_scores`: from `tools_lighthouse/audit/audit_runner.md`
- `page_source`: optional path to generated source

### Returns
- `score`: float 0–1 for the SEO category
- `passed`: boolean — `score == 1.0` and no failed audits
- `corrections`: list of `{file?, selector?, issue, required_change, priority}`

### Side effects
- Logs verdict to `safety-control/mutual_check/audit_logger.md`

## Decision Flow

1. **Extract SEO score** — read `category_scores.seo`; if missing, default to 0.
2. **Early exit** — if `score == 1.0`, return `passed=true`.
3. **Map audits to corrections** — for each failed SEO audit:
   - `document-title` / `meta-description` → add unique `<title>` and `<meta name="description">`
   - `meta-viewport` → ensure `<meta name="viewport" content="width=device-width, initial-scale=1">`
   - `canonical` → add `<link rel="canonical" href="...">`
   - `hreflang` → add `hreflang` links for multilingual pages if applicable
   - `heading-order` / `multiple-h1` → enforce single `<h1>` per page, no skipped levels
   - `image-alt` → route through `ResponsivePicture` with mandatory `alt`
   - `jsonld` / `structured-data` → inject `<script type="application/ld+json">` with `Product`, `Organization`, `WebSite`, or `BreadcrumbList` schema
   - `links-crawlable`, `is-crawlable` → avoid `onclick`-only navigation; use real `<a href>` via `SafeLink`
4. **Prioritize** — meta tags and viewport first, then headings/alt, then structured data.
5. **Return** — emit score, passed flag, corrections list.

## Failure Modes

| Condition | Response |
|---|---|
| SEO score missing | `passed=false`; corrections include generic SEO checklist |
| Structured data schema unknown | Default to `Organization` or `WebSite`; ask `plan_adjustment.md` for domain-specific schema |
| Multilingual hreflang not requested | Skip hreflang correction unless `original_request` explicitly mentions i18n |
