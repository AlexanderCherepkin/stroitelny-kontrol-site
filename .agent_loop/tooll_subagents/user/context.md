# Context

## Role
Session-state retrieval agent that assembles the operational context for a given request from conversation history, memory store, current environment state, and user profile. Provides the working memory upon which all downstream planning and execution depends.

## Contract

### Receives
- `session_id`: identifier for the current conversation or task chain
- `context_dependencies`: list of prior request IDs or memory keys from `request.md`
- `context_scope`: enum (`minimal`, `standard`, `full`) — controls how much history to retrieve
- `freshness_policy`: enum (`latest_only`, `include_stale`, `rebuild`) — how to handle outdated context
- `project_rules`: dict | None — lightweight project-level rules loaded from `project_rules.md` in workspace root

### Returns
- `assembled_context`: structured object containing recent history, relevant files, environment state, user preferences, project rules, and known limitations
- `context_completeness`: float — estimated fraction of needed context successfully retrieved
- `missing_contexts`: list of referenced but unretrievable items with reason
- `truncation_notice`: boolean — whether context was compressed to fit limits

### Side Effects
- Reads from memory store (`tools_memory/memory_store/memory_reader.md`)
- Updates session access timestamp
- May trigger `context_compressor.md` if context exceeds budget

## Decision Flow

1. **Validate session** — verify `session_id` exists; if missing, initialize new session with minimal defaults.
2. **Retrieve history** — fetch last N turns from conversation log based on `context_scope`: `minimal` = last 2 turns; `standard` = last 5 turns + summaries; `full` = full chain with compression.
3. **Resolve dependencies** — for each `context_dependencies`, fetch from memory store; if missing, record in `missing_contexts`.
4. **Load environment state** — capture current working directory, active branches, recent file changes, installed dependencies, tool availability, and load `project_rules.md` from workspace root if present; include a content hash and the rules dict under `assembled_context.project_rules`.
5. **Load user profile** — retrieve persistent preferences: language, coding style, test framework, indentation, comment policy, verbosity level.
6. **Apply freshness policy** — `latest_only` discards stale items; `include_stale` marks them with staleness warning; `rebuild` triggers re-execution of dependency queries.
7. **Compress if needed** — if assembled context exceeds token budget, invoke `tools_memory/memory_store/context_compressor.md` to summarize older turns while preserving critical constraints and decisions.
8. **Validate completeness** — compare retrieved context against known requirements for `request_type`; compute `context_completeness`.
9. **Return** — emit `assembled_context`, `context_completeness`, `missing_contexts`, `truncation_notice`.

## Failure Modes

| Condition | Response |
|---|---|
| Session ID corrupted or unparseable | Initialize fresh session; return `context_completeness=0.5`; flag `missing_contexts` |
| Memory store unreachable | Return context from local session cache only; `truncation_notice=true`; queue sync retry |
| Dependency references circular loop | Break at depth 5; log cycle to `audit_logger.md`; include truncated reference |
| Context compression corrupts critical constraint | Re-compress with constraint-preserving priority; if still corrupt, `context_completeness=0.9` with warning |
| `project_rules.md` missing or unreadable | Set `project_rules=None`; log to `audit_logger.md`; continue |
| `project_rules.md` malformed | Parse valid sections; log malformed lines; set `project_rules` to valid subset |
| Environment state snapshot fails | Use last known snapshot; mark `missing_contexts=["ENVIRONMENT_SNAPSHOT"]`, set staleness warning |
