# Terminal State

## Role
Tracks the complete state of a terminal session at every moment. CWD, environment, exit code of last command, cursor position — everything needed to understand "where am I and what just happened?"

## Contract
- **Receives**: `{ session_id, events: [{ type: "output"|"prompt"|"command_sent"|"exit_code" }] }`
- **Returns**: `{ state: { cwd, env_vars: { key: value }, last_exit_code, cursor_position, mode: "normal"|"insert"|"visual", running_process: pid|null } }`
- **Side effects**: none (pure state tracking — reads from session, updates internal model)

## Decision Flow

1. **Track CWD**
   - Intercept `cd` commands → update CWD
   - Periodically verify: send `pwd` or echo `$PWD` (invisible to user)
   - Directory pushed/popped (`pushd`/`popd`) → maintain stack
   - If CWD was deleted externally → detect, flag

2. **Track environment**
   - On session start: capture initial env
   - Intercept `export`, `set`, `setenv` → update tracked env
   - On env change: diff old vs new, record delta
   - Sensitive vars: track presence but redact value (SECRET=***)

3. **Track last exit code**
   - After every command: capture `$?` or `%ERRORLEVEL%`
   - Store: exit code + command that produced it
   - Previous exit code available for `&&` / `||` logic decisions

4. **Track prompt/cursor**
   - Detect prompt pattern (regex from shell: `$ `, `# `, `> `, `%~ `)
   - Track: prompt = shell is idle, no prompt = command running
   - Track cursor position for ANSI operations

5. **Track running process**
   - Detect foreground process (command running, shell blocked)
   - Detect background processes (jobs)
   - Know when the shell is "ready for next command"

## Failure Modes
| Condition | Response |
|---|---|
| CWD detection fails (pwd not available) | Last known CWD + flag "unverified" |
| Env changed externally (not via tracked mechanism) | Detect during periodic check, sync full env |
| Prompt pattern changed (custom PS1 after session start) | Re-detect prompt pattern |
| Foreground process stuck (no output, no prompt) | Timeout detection → flag "shell unresponsive" |
