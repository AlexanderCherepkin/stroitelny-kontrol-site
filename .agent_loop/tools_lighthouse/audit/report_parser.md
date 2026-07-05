# Lighthouse Report Parser

## Role
Compresses the 300–500 KB raw Lighthouse JSON into a token-efficient failure summary. Keeps only failed or non-perfect audits, extracts actionable fields, and drops everything that scores 100%.

## Contract

### Receives
- `raw_report_path`: absolute path to the gzipped Lighthouse JSON from `tools_lighthouse/audit/audit_runner.md`
- `score_threshold`: float — keep audits with score below this value (default 1.0, i.e., only imperfect audits)
- `max_items_per_audit`: integer — cap `details.items` length to avoid token bloat (default 5)

### Returns
- `failure_summary`: structured object per category with `score`, `failed_audits[]`, `total_weight`
- `passed`: boolean — true if no failed audits remain (all categories at 100%)
- `parsed_path`: absolute path to the filtered JSON written for downstream agents

### Side effects
- Writes filtered failure JSON to `<workspace>/.tmp/lighthouse/<session_id>/failures-<timestamp>.json`
- Logs parse summary to `safety-control/mutual_check/audit_logger.md`

## Decision Flow

1. **Load report** — read and decompress `raw_report_path`.
2. **Validate schema** — confirm top-level keys `categories`, `audits`, `configSettings` exist; if not, return empty failure summary.
3. **Iterate categories** — for each of `performance`, `accessibility`, `best-practices`, `seo`:
   - record `category.score`
   - collect `auditRefs` and map to `audits` entries
4. **Filter audits** — keep only audits where `score !== null && score < score_threshold`.
5. **Extract fields** — for each kept audit keep only:
   - `id`, `title`, `description`
   - `score`, `scoreDisplayMode`
   - `details.items` trimmed to `max_items_per_audit` (only `node`, `selector`, `url`, `source`, `wastedBytes`, `wastedMs`, `totalBytes` fields)
   - `numericValue` / `numericUnit` when present
6. **Build category summary** — group kept audits by category, compute `failed_count`.
7. **Determine passed** — `passed=true` when all categories score 1.0 and `failed_count==0`.
8. **Write filtered JSON** — save compact failure summary to `parsed_path`.
9. **Return** — emit `failure_summary`, `passed`, `parsed_path`.

## Failure Modes

| Condition | Response |
|---|---|
| Raw report missing or unreadable | `passed=false`; `failure_summary` includes parse error; log to `audit_logger.md` |
| Report schema unsupported | `passed=false`; emit minimal summary with schema version warning |
| Every audit fails (massive failure) | Keep top-N by weight/priority; cap output to token budget; flag `mass_failure` |
| Details.items missing or malformed | Skip items field; keep title/description/score |
| All categories perfect | `passed=true`; `failure_summary` empty; still write empty JSON to `parsed_path` |
