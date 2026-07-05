# Backend Spec Bridge — Plan V1

## Vision
Add a second semantic source to the Figma-to-Next.js pipeline so the system can generate not only UI, but also a matching backend layer (Prisma schema, Next.js API routes, Server Actions, and UI↔backend mappings). Figma describes visual intent; the Backend Spec Bridge supplies business rules, data types, integrity constraints, and endpoint contracts.

## V1 Scope
Supported backend specification inputs:
- OpenAPI 3.x (JSON or YAML)
- Prisma schema (`schema.prisma`)
- Structured text brief (JSON with `entities` / `fields` / `endpoints`)

Out of V1 scope: image-based ERD diagrams, natural-language-only briefs without structure, non-PostgreSQL databases.

## Output Artifacts
- `backend_mapping.json` — semantic mapping table: UI nodes ↔ endpoints ↔ models ↔ fields, plus confidence scores.
- `prisma/schema.prisma` — validated/generated Prisma model layer (new file or merge patch).
- `src/app/api/[entity]/route.ts` — Next.js App Router API routes (GET / POST / PUT / DELETE).
- `src/app/actions/[entity]Action.ts` — Next.js Server Actions for forms and mutations.
- `src/lib/dto.ts` (optional V1) — shared Zod schemas derived from OpenAPI/Prisma types.

## Architecture

### New Core Module
`figma-agent-core/backend_bridge.py`
- `OpenApiParser` — parses `paths`, `operations`, `requestBody`, `responses`, `components.schemas` into normalized `Endpoint` and `ModelField` objects.
- `PrismaParser` — lightweight line-based parser for `model`, `enum`, `datasource`, `generator`, fields, types, attributes (`@id`, `@default`, `@unique`, `?` optional), without WASM dependencies.
- `TextSpecParser` — parses structured JSON brief into the same normalized model.
- `SemanticMapper` — matches Figma text labels / input placeholders / section names against backend fields and endpoints using exact → fuzzy → keyword heuristics; produces `backend_mapping.json`.
- `PrismaGenerator` — writes/merges `schema.prisma`.
- `RouteGenerator` — writes `route.ts` files using `NextRequest` / `NextResponse.json` and a shared `prisma` client import.
- `ActionGenerator` — writes `action.ts` files with `'use server'`, async functions, `revalidatePath`, and type-safe payloads.
- `BackendBridge.run(spec_inputs, layout_ast)` — orchestrates parse → map → generate → write registry.

### New MCP Server
`mcp_servers/backend_server.py` — `BackendMCPServer`
Tools:
- `backend_analyze_spec` — parse OpenAPI/Prisma/text into normalized JSON.
- `backend_map_ui` — accept Tailwind AST + spec → return `backend_mapping.json`.
- `backend_generate_routes` — generate `route.ts` from normalized spec.
- `backend_generate_actions` — generate Server Actions from normalized spec + mapping.
- `backend_sync_schema` — write/update `prisma/schema.prisma`.
- `backend_run_bridge` — full bridge in one call.

### Integration into Existing Pipeline
- `conductor.py`:
  - New stage `backend_bridge` (runs after `layout`, before `compose`).
  - New CLI args: `--openapi`, `--prisma`, `--backend-spec-text`, `--backend-output-dir`, `--backend-mapping-file`.
  - `stage_layout` receives `--backend-mapping` if mapping exists.
  - `stage_compose` receives unchanged AST; backend hints are already embedded by layout engine.
- `layout_engine.py`:
  - Load `backend_mapping.json`.
  - Tag form-like containers with `backend_action`, `backend_endpoint`, `backend_model`.
  - Tag text inputs with `backend_field`, `input_type`, `required`, `zod_validator`.
  - Propagate mapping into `TailwindNode.to_dict()`.
- `page_composer.py`:
  - For nodes with `backend_action`, render `<form action={...}>` wrapper and `action` import.
  - For input-like nodes (`input`, `textarea`, `select`), add `name={fieldName}` and `required` if applicable.
  - For table/list nodes, add data-fetch import from generated API route or action.

### Agent Specs
- New `.agent_loop/tooll_subagents/planning/backend_spec_bridge.md` — Algorithmic template (Role, Contract, Decision Flow, Failure Modes).
- Update `.agent_loop/tooll_subagents/user/design_intake.md` to accept backend specs alongside Figma input.
- Update `.agent_loop/tooll_subagents/planning/design_to_code_planner.md` to include backend artifacts in `generated_code` and `handoff_package`.
- Update `.agent_loop/tooll_subagents/planning/tool_plan_selection.md` to include `backend` MCP category tools.
- Update `.agent_loop/ARCHITECTURE.md` and `.agent_loop/TECHNICAL_ASSIGNMENT.md` counts and pipeline description.

### Tests
- `tests/backend/fixtures/openapi_leads.yaml` / `prisma_leads.prisma` / `spec_text_leads.json`
- `tests/backend/test_backend_bridge.py` — parser unit tests, mapper accuracy tests, generator output tests.
- `tests/backend/test_layout_engine_backend.py` — mapping propagation to AST.
- `tests/backend/test_page_composer_backend.py` — form action / input name rendering.
- `tests/mcp/test_backend_server.py` — tool registration and script invocation mocks.

## Data Flow
```
User provides:
  Figma URL/JSON  +  OpenAPI/Prisma/Text Spec
    ↓
design_intake.md  →  design_descriptor + backend_spec_descriptor
    ↓
figma_design_analyst.md (Figma pipeline)
backend_spec_bridge.md   (backend pipeline)
    ↓
layout_engine.py uses backend_mapping.json
    ↓
page_composer.py renders forms with actions and inputs with names
    ↓
conductor.py runs full pipeline end-to-end
```

## Acceptance Criteria
- `backend_bridge.py --openapi fixtures/openapi_leads.yaml --layout layout_ast.json` produces `backend_mapping.json` with mapping accuracy ≥ 90% for standard fields (string, number, date, email).
- Generated `route.ts` and `action.ts` pass `tsc --noEmit` (syntax-level) and `eslint` (project rules).
- Generated/updated `schema.prisma` passes `prisma validate`.
- `conductor.py --all --openapi fixtures/openapi_leads.yaml` produces a working Next.js app where a Figma contact form posts to a generated Server Action/API route.
- `pytest tests/backend tests/mcp tests/figma -q` remains green (existing tests must not regress).
- Validators: `validate_consistency.js` 0 errors, `validate_cross_references.js` 0 broken links.
- `graphify update .` executed and graph artifacts refreshed.

## Tracker Tasks
1. Create `figma-agent-core/backend_bridge.py` parser + mapper + generators.
2. Add backend fixtures and unit tests (`tests/backend/`).
3. Create `mcp_servers/backend_server.py` and register it in `mcp_servers/bootstrap.py` / registry.
4. Integrate backend stage into `conductor.py`.
5. Update `layout_engine.py` to consume `backend_mapping.json`.
6. Update `page_composer.py` to render forms/actions/inputs with backend hints.
7. Create agent spec `backend_spec_bridge.md` and update related agent specs + architecture docs.
8. Add memory file + run validators + update graphify.
