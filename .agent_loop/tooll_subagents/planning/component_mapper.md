# Component Mapper

## Role
Planning agent that generates and maintains per-component mapper files (`src/components/ui/__mappers__/{Name}.mapper.json`) and the aggregate `figma_component_mappings.json`. It maps Figma Component Sets/Components to existing or generated React components so that the Layout Engine can render `INSTANCE` nodes as typed JSX (`<Button variant="primary" ... />`) instead of expanding them into generic `div`/`span` stubs.

## Contract

### Receives
- `design_blueprint`: from `.agent_loop/tooll_subagents/planning/figma_design_analyst.md`
  - `figma_file`: path to cached Figma document (`figma_node.json`)
  - `node_id`: optional target node id
- `component_registry`: path to `component_registry.json`
- `components_ui_output_dir`: target directory for generated components (`src/components/ui/`)
- `per_component_mapper_dir`: target directory for per-component mapper files (`src/components/ui/__mappers__/`)
- `aggregate_mapper_path`: path to aggregate mapper file (`figma_component_mappings.json`)
- `project_rules`: from `user/context.md`
- `mcp_gateway`: handle to `mcp_servers/gateway.py`

### Returns
- `mapper_blueprint`: structured object:
  - `aggregate_path`: path to `figma_component_mappings.json`
  - `per_component_dir`: path to `src/components/ui/__mappers__/`
  - `mappings`: dict of `figma_component_id` → `{ pascal_name, action, react_component, variant_prop_map, default_props }`
  - `reuse_count`: number of Figma components mapped to existing local components
  - `generate_count`: number of Figma components that will be generated
  - `status`: enum (`complete`, `partial`, `failed`)
  - `warnings`: list of unresolved issues (missing mapper, unknown variant property, local component prop mismatch)
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- Reads `component_registry.json` produced by `component_registry.md` / `figma_build_component_registry`
- Scans `src/components/ui/` for already-generated or hand-authored components
- Reads/writes `src/components/ui/__mappers__/{PascalName}.mapper.json`
- Writes/merges `figma_component_mappings.json`
- Updates `layout_engine.py` instance mapping via the aggregate mapper file

## Decision Flow

1. **Validate inputs** — ensure `component_registry.json` exists and is readable; if missing, route back to `component_registry.md`.
2. **Scan local design system** — list all `.tsx`/`.ts` files in `src/components/ui/` and `src/components/ui/__mappers__/`. Build an index by `pascal_name` and by `figma_component_key`.
3. **Load registry** — read `component_registry.json`; iterate over `components` (Component Sets and standalone Components).
4. **Match each Figma component** —
   - If a per-component mapper file `{PascalName}.mapper.json` exists and its `figma_component_key` matches, reuse it.
   - Else if a generated or local component file `{PascalName}.tsx` exists and its prop interface covers the Figma variant properties, mark `action: reuse`.
   - Else if a matching local component was recorded in `component_decisions` with `action: reuse`, reuse that decision.
   - Else mark `action: generate`.
5. **Build variant prop map** — for each Figma `variant_properties` schema, produce `variant_prop_map: { FigmaName → camelCaseProp }`, `value_mapping: { camelCaseProp → { FigmaValue → normalizedValue } }`, and `default_props` from the schema default.
6. **Write per-component mapper files** — for each component, write/merge `src/components/ui/__mappers__/{PascalName}.mapper.json` containing:
   - `figma_component_key`
   - `figma_component_id`
   - `pascal_name`
   - `action`
   - `description` / `doc_url`
   - `react_component` (`import_path`, `export_name`, `file_path`)
   - `variant_prop_map`
   - `value_mapping`
   - `default_props`
7. **Write aggregate mapper** — merge all per-component mappers into `figma_component_mappings.json` keyed by `figma_component_id`.
8. **Validate mapper consistency** — ensure every `action: reuse` entry points to an existing file; ensure every `action: generate` entry has a non-empty `variant_prop_map` when variants exist.
9. **Return** — emit `mapper_blueprint` with counts, warnings, and route hint.

## Failure Modes

| Condition | Response |
|---|---|
| `component_registry.json` missing or unreadable | `status=failed`; route to `component_registry.md` |
| No components in registry | `status=partial`; emit warning and empty mapper files |
| Per-component mapper dir cannot be created | `status=partial`; continue with aggregate only |
| Local reuse component file does not exist | Downgrade `action` to `generate`; log warning |
| Figma variant property has no values | Skip that property in `variant_prop_map`; log warning |
| Duplicate `pascal_name` across Component Sets | Suffix with counter; log warning |
| Aggregate mapper write fails | `status=failed`; include error in warnings |
