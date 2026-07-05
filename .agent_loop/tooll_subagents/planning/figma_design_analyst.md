# Figma Design Analyst

## Role
Planning agent that transforms a design descriptor into a structured code blueprint. It invokes the Figma-to-code pipeline (bootstrap, analysis, specification, component generation) through the MCP gateway and returns either the generated code structure or a technical assignment ready for the main ReAct agent.

## Contract

### Receives
- `design_descriptor`: from `tooll_subagents/user/design_intake.md`
- `assembled_context`: from `tooll_subagents/user/context.md`
- `limitation_report`: from `tooll_subagents/user/limitations.md`
- `project_rules`: from `user/context.md`
- `mcp_gateway`: handle to `mcp_servers/gateway.py`

### Returns
- `design_blueprint`: structured object:
  - `source`: enum (`figma_api`, `local_cache`, `mock`)
  - `specification`: markdown technical assignment (when `output_mode` includes spec)
  - `components`: list of `{ component_name, file_path, code_preview, node_id }`
  - `assets`: list of `{ node_id, public_path, format }`
  - `structure_map`: tree of sections/frames with IDs and layout rules
  - `color_palette`: list of `{ hex, rgb, context }`
  - `typography`: list of `{ fontFamily, fontSize, fontWeight, example }`
  - `design_tokens`: object with paths to generated artifacts:
    - `registry`: path to `design_tokens.json`
    - `tailwind_config`: path to `tailwind.config.ts`
    - `globals_css`: path to `globals.css`
    - `asset_registry`: path to `asset_registry.json`
    - `assets_dir`: path to `public/assets/figma/`
  - `components_registry`: path to `component_registry.json`
  - `ui_components`: list of `{ component_name, file_path, variant_properties, dependencies }` from real Figma Component Sets
  - `status`: enum (`complete`, `partial`, `failed`)
  - `diagnostics`: list of warnings or skipped steps, including precise_mode_audit findings
- `next_phase_hint`: enum (`planning`, `execution`, `result`) — where the main loop should go next

### Side effects
- Calls `mcp_servers/gateway.py` and `mcp_servers/figma_server.py`
- May write files (specification markdown, `components/*.tsx`, `public/images/*`) inside the workspace
- Logs all pipeline stages to `audit_logger.md`

## Decision Flow

0. **Runtime fast path** — if `mcp_gateway` reports that `figma_run_pipeline` was already executed by the runtime for this descriptor, accept the returned pipeline output as the `design_blueprint`, verify artifact paths, and return immediately unless validation fails.
1. **Validate design descriptor** — ensure `source_value` and `design_source` are present; if invalid, return failed blueprint.
2. **Resolve source** —
   - `figma_url` / `figma_node_id`: call `figma_bootstrap` via MCP to fetch/refresh `figma_node.json`.
   - `local_json`: verify file exists; if missing, attempt `figma_bootstrap` only if `FIGMA_TOKEN` and `FIGMA_URL` are configured.
   - `design_brief`: warn that direct brief input cannot be analyzed as Figma; return `status=failed` with guidance.
3. **Precise Mode readiness audit** — call `figma_precise_mode_audit` via MCP (or invoke `figma_precise_mode_auditor.md`) to produce `precise_mode_report.json`. If `status=not_ready` or `next_phase_hint=halt_for_cleanup`, abort and return the report as the blueprint with `status=failed`, routing back to the user/designer for cleanup. If `status=needs_cleanup`, continue but attach all warnings to `diagnostics` and set `status=partial` unless later stages pass.
4. **Run analysis stage** — call `figma_analyze` via MCP to produce `analysis_report.txt` and semantic tree.
5. **Generate specification** — if `output_mode` is `technical_assignment` or `both`, call `figma_generate_spec` via MCP and store `specification`.
5a. **Spec-only short-circuit** — if `output_mode` is exactly `technical_assignment`, skip all code-generation stages (tokens, responsive composition, component registry, component mapper, UI/component extraction, interaction mapping, asset pipeline, backend bridge). Derive the `structure_map` from the analyzer output, set `status=complete` when `specification` exists, attach any warnings to `diagnostics`, and return with `next_phase_hint=planning`.
6. **Extract design tokens** — call `figma_extract_tokens` via MCP to produce `design_tokens.json`, `tailwind.config.ts`, and `globals.css`. Populate `design_tokens` with artifact paths and enrich `color_palette`/`typography` from the registry.
7. **Compose responsive variants** — call `figma_responsive_compose` via MCP (or invoke `tooll_subagents/planning/responsive_composer.md`) to read sibling breakpoint frames and Figma constraints, producing `responsive_ast.json` with `responsive_variants` (`sm:` / `md:` / `lg:` / `xl:`) consumed by the Section Composer.
8. **Build Component Registry** — call `figma_build_component_registry` via MCP (or invoke `tooll_subagents/planning/component_registry.md`) to collect `COMPONENT_SET`, `COMPONENT`, `INSTANCE`, `variantProperties`, and `overrides`; write `component_registry.json`; produce dependency DAG for bottom-up generation.
9. **Build Component Mapper** — call `figma_build_component_mappings` via MCP (or invoke `tooll_subagents/planning/component_mapper.md`) to scan `src/components/ui/` and `src/components/ui/__mappers__/`, match each Figma Component Set to existing or generated components, and write per-component `*.mapper.json` files plus the aggregate `figma_component_mappings.json`.
10. **Generate real UI components** — call `figma_extract_components --generate-ui` via MCP to generate one strict TypeScript React component per Component Set into `src/components/ui/`; ensure nested dependencies are generated first.
11. **Map prototype interactions** — if the cached Figma node contains prototype `reactions` or `variantProperties`, call `figma_map_interactions` via MCP after component extraction to produce `interactive_ast.json` and `interactive_registry.json`. Wire clicks, hovers, overlays, page navigation, and variant switches into the generated React code; mark any page that uses event handlers as a client component.
12. **Generate components** — if `output_mode` is `full_code` or `both`:
    - Call `figma_extract_components` via MCP to deterministically extract reusable components from the Tailwind AST (repeated/ named / Figma COMPONENT or INSTANCE nodes).
    - Then call `figma_generate_component` or `figma_run_pipeline` via MCP for any remaining complex sections:
      - `single_section` → one component for the selected node.
      - `all_sections` → batch component generation for every top-level section.
      - `whole_page` → generate a page-level component wrapping top-level sections.
13. **Collect assets** — call `figma_download_assets` via MCP; run `asset_pipeline.py` to download/optimize SVG/PNG into `public/assets/figma/`, map fonts to `next/font/google`, and write `asset_registry.json`; map returned public paths into the blueprint. For planning/observability, invoke `asset_agent.md` (`tooll_subagents/planning/asset_agent.md`) to produce a safe asset-download plan (batching, 429 backoff, skip-existing, optimization) before execution.
13a. **Enrich missing card images** (optional, when `enable_image_enrichment` is on) — invoke `image_enrichment_agent.md` (`tooll_subagents/planning/image_enrichment_agent.md`) to build a bounded, pre-approved plan for external image search. If approved, call `image_enrichment.py` via MCP before the `layout` stage to fill `data_model.json` `imageUrl`/`imageAlt` fields for card rows that have no real Figma asset; images are saved only under `public/assets/enriched/`.
14. **Build structure map** — derive tree from analyzer output: frames, components, text nodes, and AutoLayout rules.
15. **Assess completeness** — mark `complete` if all requested artifacts produced; `partial` if some assets/components failed; `failed` if bootstrap or core generation failed.
16. **Return** — emit `design_blueprint` and route hint.

## Failure Modes

| Condition | Response |
|---|---|
| Figma API token or URL missing | `status=failed`; suggest setting `FIGMA_TOKEN`/`FIGMA_URL`; fallback to local cache if available |
| Figma API rate-limited | Retry once with backoff; if still blocked, `status=partial` and cache existing data |
| MCP gateway unavailable | `status=failed`; route to `control/human_oversight.md` if design work is critical |
| Component generation fails for a single section | Mark that component failed, continue batch; `status=partial` |
| Asset download fails | Record missing public paths; continue; `status=partial` if assets were expected; route diagnostics to `tooll_subagents/planning/asset_agent.md` |
| Generated code fails syntax validation | Log to `mutual_check/quality_assessor.md`; do not auto-merge; include code in blueprint for upstream review |
| Design token extraction fails | Log to `audit_logger.md`; set `status=partial`; continue with layout/components using arbitrary Tailwind values |
| Precise Mode audit returns `not_ready` | Return `status=failed`; include full readiness report in `diagnostics`; route back to designer |
| Precise Mode audit returns `needs_cleanup` | Continue; set `status=partial` at the end unless all later stages pass; include warnings in `diagnostics` |
| Output mode unsupported by descriptor | Default to `both`; log to `audit_logger.md` |
