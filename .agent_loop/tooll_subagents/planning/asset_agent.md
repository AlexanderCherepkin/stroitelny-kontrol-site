# Asset Agent

## Role

Planning and orchestration agent for the Figma asset-download sub-pipeline. It turns a list of discovered image/SVG/font assets into a safe, deterministic execution plan: batch Figma API requests, respect rate limits, skip already-downloaded files, run optimization, and emit a public-path registry. It does not perform I/O itself; it delegates to `tools_web/web_request/retry_manager.md` for network policy and to `tools_runcom/run_command.md` for invoking the production `asset_pipeline.py` / `figma_http_client.py` scripts.

## Contract

### Receives
- `asset_list`: list of `{node_id, name, ref, format, type, width?, height?}` from upstream Figma design analysis or direct Figma structure analysis.
- `figma_descriptor`: object with `file_key`, `token_env` (e.g. `FIGMA_TOKEN`), `figma_url`.
- `output_dir`: target directory inside `public/` (default `public/assets/figma`).
- `registry_file`: path for `asset_registry.json` (default `asset_registry.json`).
- `project_rules`: from `user/context.md` — tooling preferences and allowed domains.
- `execution_policy`: enum (`speed_priority`, `accuracy_priority`, `cost_priority`, `safety_priority`) from `tool_plan_selection.md`.
- `skip_existing`: boolean — reuse locally cached assets (default `true`).

### Returns
- `asset_plan`: ordered plan containing:
  - `batches`: list of `{node_ids, format, scale, delay_ms}` — sized to stay under Figma rate limits.
  - `optimization_steps`: list of `{file, tool, fallback}` (`svgo` for SVG, `sharp` for PNG/JPEG when available).
  - `registry_update`: path to write `asset_registry.json`.
  - `expected_public_paths`: dict `ref` → `/assets/figma/...` for downstream layout/component generation.
- `risk_flags`: list of warnings (e.g. too many assets, missing token, large raster dimensions).
- `next_phase_hint`: enum (`execution`, `planning`, `result`) — default `execution`.

### Side Effects
- Reads `asset_registry.json` and local files to detect existing assets (read-only during planning).
- Writes planning artifacts only if explicitly asked; real downloads happen later in `execution`.
- Logs plan to `audit_logger.md`.

## Decision Flow

1. **Validate inputs** — require `figma_descriptor.file_key` and a configured token env; if missing, set `risk_flags=[missing_token]` and `next_phase_hint=planning`.
2. **Deduplicate assets** — collapse assets by `ref` so the same image fill is not downloaded twice.
3. **Check existing cache** — for each asset, check whether a file matching `*{node_id}.{format}` already exists in `output_dir`. If `skip_existing=true`, mark cached assets as skipped in the plan.
4. **Apply batching policy** — group remaining Figma image API requests into chunks of ≤25 node IDs (Figma Images API limit). For SVG vectors, plan individual `GET` of vector data or rely on `figma_download_assets` MCP stage.
5. **Assign rate-limit windows** — insert `delay_ms` between batches (default 1000ms) and set `max_retries=5` with exponential backoff honoring `Retry-After`. Reference `tools_web/web_request/retry_manager.md` for backoff math.
6. **Plan optimization** — mark SVG assets for `svgo`, raster assets for `sharp` resize/WebP conversion only when `sharp` is installed and `project_rules` allows WebP; otherwise keep original PNG/JPEG.
7. **Plan font mapping** — collect `fontFamily` values; if a family exists in the known Google Fonts set, emit `next/font/google` import plan; otherwise flag as system fallback.
8. **Estimate cost/risk** — if asset count > 200 or total estimated bytes > 50MB, add `risk_flags=[large_asset_volume]` and recommend `execution_policy=cost_priority`.
9. **Validate safety scope** — ensure `output_dir` is under project `public/`; if not, set `next_phase_hint=planning` and route to `control/file_system_guard.md`. Ensure Figma API host (`api.figma.com`) is in network allow-list; if not, route to `control/network_guard.md`.
10. **Return** — emit `asset_plan`, `risk_flags`, and `next_phase_hint`.

## Failure Modes

| Condition | Response |
|---|---|
| `figma_descriptor.file_key` missing | `risk_flags=[missing_file_key]`; `next_phase_hint=planning`; request clarification |
| `FIGMA_TOKEN` env not configured | `risk_flags=[missing_token]`; `next_phase_hint=planning`; do not attempt unauthorized calls |
| `output_dir` outside project `public/` | `next_phase_hint=planning`; escalate to `control/file_system_guard.md` |
| `api.figma.com` not in network allow-list | `next_phase_hint=planning`; escalate to `control/network_guard.md` |
| Duplicate `ref` values with conflicting formats | Keep first, log warning, include both expected paths in registry |
| `sharp`/`svgo` unavailable | Mark optimization as skipped; do not fail the plan; record in `risk_flags` |
| Figma 429 even after max retries | Mark affected batch as failed; include partial URLs in registry with `status=failed`; continue other batches |
| Asset list empty | Return empty `asset_plan` with `next_phase_hint=execution` and note that no I/O is needed |
