# Request

## Role
Entry-point intake agent that captures, parses, and classifies the raw user request into a structured, machine-understandable task descriptor. Serves as the bridge between the external user and the internal ReAct cycle.

## Contract

### Receives
- `raw_request`: free-text, image, or structured payload from user interface
- `source_channel`: enum (`chat`, `cli`, `api`, `voice`, `batch`)
- `session_id`: identifier for conversation context
- `priority_hint`: optional enum (`critical`, `high`, `normal`, `low`)

### Returns
- `parsed_request`: structured task descriptor containing intent, entities, constraints, and success criteria
- `request_type`: enum (`code_change`, `question`, `debug`, `refactor`, `design`, `documentation`, `test`, `data_analysis`, `deployment`, `general`)
- `urgency`: enum (`immediate`, `standard`, `background`) — derived from content + `priority_hint`
- `context_dependencies`: list of prior request IDs or memory keys this request references
- `confidence`: float — parser certainty

### Side Effects
- Logs intake record to `audit_logger.md` via `action_logging.md`
- Initializes or updates session context in memory store

## Decision Flow

1. **Ingest payload** — decode `raw_request` (UTF-8, base64, multipart) based on `source_channel`.
2. **Language detection** — identify primary language; flag if multilingual content detected.
3. **Intent classification** — map request to `request_type` using keyword + embedding classifier; if ambiguous, attach secondary candidate with lower weight.
4. **Entity extraction** — extract named entities: file paths, function names, URLs, deadlines, constraints, forbidden actions.
5. **Constraint parsing** — identify hard constraints ("do not modify X", "must use Y library", "deadline Z") and soft preferences.
6. **Context linking** — scan for references to prior conversation turns, memory keys, or files; populate `context_dependencies`.
7. **Urgency scoring** — combine explicit `priority_hint` with implicit signals (crashes, security, broken production, user frustration markers).
8. **Validation** — check for empty intent, completely unsupported request type, or malformed input that cannot be parsed.
9. **Return structured descriptor** — emit `parsed_request`, `request_type`, `urgency`, `context_dependencies`, `confidence`.

## Failure Modes

| Condition | Response |
|---|---|
| Raw request is empty or whitespace-only | Return `parsed_request=null`, `request_type=general`, `confidence=0.0`; prompt user for clarification |
| Unsupported media type (binary, corrupted image) | Return `parsed_request=null`, `request_type=general`, `confidence=0.0`; request re-submission |
| Intent classification confidence < 0.5 | Return `request_type=general` with secondary candidates; flag `internal_monologue.md` for ambiguity handling |
| Language unsupported by system | Return `parsed_request` with best-effort translation; flag `assistance_request.md` for human review |
| Session context store unavailable | Parse request statelessly; queue context update for retry; log to `action_logging.md` |
