# Design Intake

## Role
Intake agent that recognizes when the incoming user request is a design project (Figma file, design JSON, or design brief) and converts it into a structured design descriptor for downstream analysis. It is the entry gate that turns visual/design input into the Agentic Loop's native planning format.

## Contract

### Receives
- `raw_request`: free-text, URL, JSON payload, or file path from the user interface
- `source_channel`: enum (`chat`, `cli`, `api`, `voice`, `batch`, `design_drop`)
- `session_id`: identifier for conversation context
- `priority_hint`: optional enum (`critical`, `high`, `normal`, `low`)
- `project_rules`: dict | None — lightweight project-level rules from `project_rules.md`

### Returns
- `request_type`: enum (`design_project`, `code_change`, `question`, `debug`, `refactor`, `documentation`, `test`, `general`)
- `design_descriptor`: structured object present only when `request_type=design_project`:
  - `design_source`: enum (`figma_url`, `figma_node_id`, `local_json`, `design_brief`)
  - `source_value`: the URL, node ID, file path, or brief text
  - `output_mode`: enum (`technical_assignment`, `full_code`, `both`) — what the user wants back
  - `target_stack`: optional enum (`react_next_tailwind`, `vue_nuxt`, `svelte`, `plain_html`, `infer_from_rules`)
  - `target_scope`: enum (`single_section`, `all_sections`, `whole_page`)
  - `backend_spec`: optional structured object:
      - `spec_type`: enum (`openapi`, `prisma`, `structured_text`)
      - `spec_path`: path to OpenAPI YAML/JSON, Prisma schema, or structured JSON brief
    - `metadata`: `{ title, detected_language, has_assets, has_components, has_backend_spec }`
- `parsed_request`: structured task descriptor for non-design requests (pass-through)
- `confidence`: float 0.0–1.0

### Side effects
- Logs intake record to `audit_logger.md`
- Initializes design-specific session context in `state_manager.md`

## Decision Flow

1. **Ingest payload** — decode `raw_request` based on `source_channel` (UTF-8 text, JSON, multipart file reference).
2. **Detect design signals** — check for:
   - Figma URL patterns (`figma.com/file/`, `figma.com/design/`, `node-id=`).
   - Figma node ID patterns (`\d+:\d+`, `\d+-\d+`).
   - Local JSON files named like `figma_*.json` or `design_*.json`.
   - Backend spec signals: OpenAPI (`openapi.yaml`, `swagger.json`), Prisma (`schema.prisma`), structured JSON brief (`*_spec.json` with `entities`/`endpoints`).
   - Keywords: "макет", "дизайн", "Figma", "section", "frame", "компонент", "верстка", "React по макету", "OpenAPI", "Prisma", "backend".
3. **Classify source type** — set `design_source` and extract `source_value`.
4. **Determine output mode** — infer from request wording:
   - "ТЗ", "техническое задание", "спецификация" → `technical_assignment`.
   - "сделай код", "сверстай", "компонент", "реализуй" → `full_code`.
   - Ambiguous or both requested → `both`.
5. **Infer target stack** — use `project_rules.tooling_preferences` if present; otherwise default to `react_next_tailwind`.
6. **Infer target scope** — default to `single_section` if node ID provided, else `whole_page` or `all_sections` based on wording.
7. **Extract backend spec** — if OpenAPI/Prisma/structured spec file is found, populate `design_descriptor.backend_spec` with `spec_type` and `spec_path`; set `metadata.has_backend_spec=true`.
8. **Build fallback for non-design requests** — if no design signals, return `request_type` from conventional `request.md` classification and leave `design_descriptor=null`.
8. **Return** — emit `request_type`, `design_descriptor`, `parsed_request`, `confidence`.

## Failure Modes

| Condition | Response |
|---|---|
| Raw request is empty or whitespace-only | Return `request_type=general`, `design_descriptor=null`, `confidence=0.0`; prompt user |
| Figma URL malformed | Return `request_type=design_project` with `design_source=figma_url` and `metadata.parse_error=true`; route to `figma_design_analyst.md` for validation |
| Local design JSON missing | Return `request_type=design_project`, `metadata.file_missing=true`; attempt bootstrap via `figma_design_analyst.md` |
| Output mode ambiguous | Default to `both`; log ambiguity to `internal_monologue.md` |
| Source channel does not support design payloads | Return `request_type=general`; advise user to provide URL or file path |
| Backend spec file referenced but missing | Return `request_type=design_project` with `metadata.backend_spec_missing=true`; route to `backend_spec_bridge.md` for validation |
