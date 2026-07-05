# Backend Spec Bridge

## Role
Planning agent that ingests a backend specification (OpenAPI, Prisma schema, or structured text), maps it to UI elements discovered by the Figma pipeline, and generates a real backend layer (Prisma schema, Next.js API routes, Server Actions, and a semantic mapping registry). It is the second semantic source that turns a UI generator into a fullstack pipeline.

## Contract

### Receives
- `backend_spec_descriptor`: from `tooll_subagents/user/design_intake.md`
  - `spec_type`: enum (`openapi`, `prisma`, `structured_text`)
  - `spec_path`: path to OpenAPI YAML/JSON, Prisma schema, or structured text JSON
- `design_blueprint`: from `tooll_subagents/planning/figma_design_analyst.md` (Tailwind AST, component map, assets)
- `project_rules`: from `user/context.md`
- `mcp_gateway`: handle to `mcp_servers/gateway.py`

### Returns
- `backend_blueprint`: structured object:
  - `backend_mapping`: path to `backend_mapping.json`
  - `schema_prisma`: path to generated/updated `prisma/schema.prisma`
  - `api_routes`: list of `{ file_path, endpoint_path, methods }`
  - `server_actions`: list of `{ file_path, action_name, model }`
  - `mapping_accuracy`: float 0.0–1.0 — percent of UI fields automatically mapped to backend fields
  - `status`: enum (`complete`, `partial`, `failed`)
  - `warnings`: list of unresolved mismatches (missing required fields, extra UI fields, naming conflicts)
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- Calls `mcp_servers/backend_server.py` (`backend_run_bridge`, `backend_map_ui`, `backend_sync_schema`)
- Writes `backend_mapping.json`, `prisma/schema.prisma`, `src/app/api/*/route.ts`, `src/app/actions/*Action.ts`
- Logs mapping decisions and warnings to `audit_logger.md`

## Decision Flow

1. **Validate backend spec descriptor** — ensure `spec_type` and `spec_path` are present; if missing and Figma blueprint implies a backend (forms, tables, cards), attempt to infer a minimal spec from the UI and warn.
2. **Parse spec** — dispatch to the appropriate parser:
   - `openapi` → `backend_analyze_spec` via MCP; validate JSON/YAML structure.
   - `prisma` → `backend_analyze_spec` via MCP; parse models, enums, datasource.
   - `structured_text` → `backend_analyze_spec` via MCP; validate entity/field schema.
3. **Load UI AST** — extract the Tailwind AST from `design_blueprint.layout_ast` or `layout_ast.json`.
4. **Map UI to backend** — call `backend_map_ui` via MCP; match forms to models and inputs to fields using exact → fuzzy → keyword heuristics. Accept mappings with confidence ≥ 0.5; flag low-confidence matches.
5. **Resolve mismatches** —
   - UI field not found in backend: emit warning; if field is non-critical, pack into `metadata` JSONB suggestion; otherwise escalate to `tooll_subagents/self_correction/assistance_request.md` if required fields are missing.
   - Backend required field missing in UI: generate hidden input or system default; if no default exists, mark `status=partial` and warn.
   - Naming conflict: produce a Data Mapper inside the Server Action/API route using the mapping table.
6. **Generate artifacts** — call `backend_run_bridge` via MCP to produce:
   - `prisma/schema.prisma`
   - `src/app/api/[model]/route.ts`
   - `src/app/actions/[model]Action.ts`
7. **Assess accuracy** — compute `mapping_accuracy` from field mapping confidence scores. If < 0.9, set `status=partial` and include warnings.
8. **Return** — emit `backend_blueprint` and route hint.

## Failure Modes

| Condition | Response |
|---|---|
| Backend spec file missing or unreadable | `status=failed`; route to `assistance_request.md` for spec upload |
| Unsupported spec format | `status=failed`; log unsupported format and suggest OpenAPI/Prisma/JSON |
| MCP backend server unavailable | `status=failed`; route to `control/human_oversight.md` if backend work is critical |
| No UI forms/tables found to map | `status=partial`; still generate standalone API routes and schema from spec |
| Mapping accuracy < 0.5 | `status=partial`; include low-confidence warnings; do not auto-generate ambiguous Data Mappers |
| Generated schema fails `prisma validate` | Log to `mutual_check/quality_assessor.md`; return `status=partial`; do not merge |
| Generated TypeScript has syntax errors | Log to `mutual_check/quality_assessor.md`; return `status=partial` |
