# Command History

## Role
Records every command sent and its outcome. Full audit trail — what was typed, when, what happened, exit code, duration. Enables replay, debugging, and "what did we just do?"

## Contract
- **Receives**: `{ session_id, events: [{ type: "input"|"output"|"exit", data }] }`
- **Returns**: `{ history: [{ command, timestamp, duration_ms, exit_code, output_summary }], search: (query) => [match] }`
- **Side effects**: writes to history store (persistent across sessions)

## Decision Flow

1. **Record each command**
   - Capture: full command string, timestamp, session_id, CWD at time of execution
   - Before execution: mark status `running`
   - After execution: record exit_code, duration, output preview (first 200 chars)
   - Sanitize: never store credentials in command history (strip `--password=...`, `-p ...`, `export SECRET=...`)

2. **Deduplicate**
   - Consecutive identical commands → increment repeat count, don't duplicate entry
   - Exception: if exit codes differ between runs → keep separate entries

3. **Search**
   - By prefix: `git` → all git commands
   - By substring: `docker` → all commands mentioning docker
   - By exit code: all failed commands (exit_code != 0)
   - By time range: last hour, yesterday, this session
   - Fuzzy match for typos (edit distance)

4. **Session boundaries**
   - Each session gets a session marker in history
   - Cross-session: search across all sessions for this project
   - Export: full history as JSON/text for audit

5. **Pruning**
   - Max entries per session: 10,000
   - Max total across sessions: 100,000
   - Eviction: oldest first, but preserve failed commands (debug value)

## Failure Modes
| Condition | Response |
|---|---|
| History store full | Evict oldest entries, warn |
| History store corrupted | Rebuild from session logs, flag data loss |
| Secret detected in recorded command | Redact retroactively, flag for security review |
| Concurrent writes (two sessions) | Lock per session_id, no cross-session conflicts |
