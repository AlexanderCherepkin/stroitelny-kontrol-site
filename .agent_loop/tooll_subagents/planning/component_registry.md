# Component Registry

## Role
Planning agent that turns real Figma component semantics (`COMPONENT_SET`, `COMPONENT`, `INSTANCE`, `variantProperties`, `overrides`) into a typed React component library. It produces a `component_registry.json` pre-processor artifact, drives the Layout Engine to tag instances, and coordinates generation of one strict TypeScript React component per Component Set with bottom-up dependency resolution.

## Contract

### Receives
- `design_blueprint`: from `.agent_loop/tooll_subagents/planning/figma_design_analyst.md`
  - `figma_file`: path to cached Figma document (`figma_node.json`)
  - `node_id`: optional target node id
- `component_registry`: path to `component_registry.json` (input/output)
- `components_ui_output_dir`: target directory for generated components (`src/components/ui/`)
- `project_rules`: from `user/context.md`
- `mcp_gateway`: handle to `mcp_servers/gateway.py`

### Returns
- `components_blueprint`: structured object:
  - `registry_path`: path to `component_registry.json`
  - `ui_components`: list of `{ file_path, pascal_name, variant_properties, dependencies, action }` (`action`: `reuse` or `generate`)
  - `dependency_order`: list of component ids in bottom-up generation order
  - `instance_mappings`: list of page instances → `{ component_ref, variant_props, overrides, local_match }`
  - `status`: enum (`complete`, `partial`, `failed`)
  - `warnings`: list of unresolved issues (library components, missing variant data, cyclic dependencies)
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- Calls `mcp_servers/figma_server.py` (`figma_build_component_registry`, `figma_extract_components`)
- Writes `component_registry.json`
- Writes `src/components/ui/{PascalName}.tsx`
- Updates `layout_engine.py` instance tags via registry load

## Decision Flow

1. **Validate blueprint** — ensure `figma_file` exists; if not, request bootstrap first.
2. **Build registry** — call `figma_build_component_registry` via MCP; collect `COMPONENT_SET`, `COMPONENT`, `INSTANCE`, `variantProperties`, and `overrides`.
3. **Map to local design system** — scan `src/components/ui/` and `src/components/` for existing React/TypeScript components; normalize names and compare prop signatures against Figma variant properties. Mark each Figma component as `reuse` (map to existing file) or `generate` (create a new component). Write this decision into `component_registry.json` under `component_decisions` and `local_components`.
4. **Resolve dependencies** — build a DAG from nested instance references inside Component Sets/Components; run topological sort bottom-up.
5. **Detect cycles** — if a cycle exists, break the edge, emit a warning, and render the cyclic reference as an opaque `div`.
6. **Generate components** — call `figma_extract_components --generate-ui` via MCP (or equivalent script); ensure one React component per Component Set with a TypeScript interface derived from `variantProperties`. For `reuse` components, skip generation and record the import path instead.
7. **Tag instances** — ensure `layout_engine.py` loads `component_registry.json` and tags `INSTANCE` nodes with `component_ref`, `variant_props`, and `overrides`.
8. **Validate output** — verify generated files export a named component, compile syntactically, and that no component imports an undefined dependency.
9. **Return** — emit `components_blueprint` and route hint.

## Failure Modes

| Condition | Response |
|---|---|
| Figma document missing or unreadable | `status=failed`; route to `bootstrap` stage |
| No Component Sets or Components found | `status=partial`; fallback to pattern-based `src/app/components/` extraction |
| Instance references unknown Component Set | `status=partial`; skip instance tag and log warning |
| Cyclic component dependencies | Break cycle, render as `div`, include warning |
| Generated component fails `tsc --noEmit` | `status=partial`; route to `mutual_check/quality_assessor.md` |
| Layout engine cannot load registry | Continue without instance tagging; warn |
| Local component scan fails | `status=partial`; continue and mark all components as `generate` |
