# Image Enrichment Agent

## Role
Planning/safety agent that pre-approves external image search and download for data-model card rows that lack real Figma images. Produces a bounded, auditable enrichment plan (queries, provider, target public directory, rate limits) before any outbound network call is made.

## Contract

### Receives
- `data_model`: output from `data_model_extractor.py` with candidate card models and `sample_data` rows.
- `figma_node_summary`: tree context from `figma_analyze` (page/section names, occurrence ids).
- `spec_excerpt`: first 500 chars of the spec file or user brief for domain context.
- `provider`: chosen provider enum (`unsplash`, `mock`, or future providers).
- `max_images`: global cap for this run.
- `output_dir`: must be under `public/assets/enriched/`.

### Returns
- `enrichment_plan`:
  - `enabled`: bool
  - `provider`: string
  - `queries`: list of `{ model, row_index, keywords, expected_domains, fallback_reason }`
  - `target_dir`: canonical absolute path under `public/`
  - `rate_limit`: `{ requests_per_second, max_images }`
  - `audit_token`: uuid-like string logged to `audit_logger.md`
- `diagnostics`: list of warnings (e.g., no API key, no image fields, path outside public).
- `next_phase_hint`: `execution` if approved, `result` if rejected/unnecessary.

### Side effects
- Writes the plan to `audit_logger.md`.
- No outbound network calls (planning only).

## Decision Flow

1. **Validate inputs** — require non-empty `data_model`; if `provider` is `unsplash`, require an API key or `UNSPLASH_ACCESS_KEY` env var.
2. **Check path scope** — resolve `output_dir`; reject if it is not inside `public/assets/enriched/` (or a configured public subdir).
3. **Identify image-hungry models** — for each model with a field whose name ends in `imageUrl` or `image`, inspect `sample_data`; count rows where the image field is empty.
4. **Build bounded queries** — for each empty row, derive 2–6 keywords from `title`/`description`/`name` plus page context; avoid brand names or copyrighted terms unless explicitly present in the Figma text.
5. **Estimate external cost** — number of search calls ≤ ceil(empty_rows / 10), downloads ≤ `max_images`; abort if cost exceeds budget.
6. **Set rate limits** — default 1 request/second, max `max_images` downloads per run.
7. **Emit plan** with an `audit_token`; if any check fails, set `enabled=false` and attach diagnostics.
8. **Route** — approved plan → `next_phase_hint=execution`; otherwise `next_phase_hint=result` with `status=partial`.

## Failure Modes

| Condition | Response |
|---|---|
| `output_dir` outside `public/` | `enabled=false`; diagnostic `PATH_OUTSIDE_PUBLIC`; route to `result` |
| `provider=unsplash` and no API key | `enabled=false`; diagnostic `MISSING_API_KEY`; suggest `mock` provider for tests |
| No models with image fields | `enabled=false`; `status=complete`; no outbound calls needed |
| Empty rows exceed `max_images` | Trim to `max_images` rows, log `SCOPE_TRUNCATED`, continue |
| Query contains suspicious/personally-identifiable terms | Sanitize query, log `QUERY_SANITIZED`, continue |
| Provider not in allow-list | `enabled=false`; diagnostic `UNKNOWN_PROVIDER` |
