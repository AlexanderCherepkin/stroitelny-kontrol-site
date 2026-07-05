# Error Analyzer

## Role
Interprets command failures. Translates exit codes, stderr messages, and signal deaths into actionable diagnoses. "Command failed" is useless — "missing dependency: libssl.so.3, install via apt" is useful.

## Contract
- **Receives**: `{ exit_code, signal, stdout, stderr, command, platform }`
- **Returns**: `{ success: bool, error_type: string, diagnosis: string, suggestion: string|null, recoverable: bool }`
- **Side effects**: none (pure analysis)

## Decision Flow

1. **Classify outcome**
   - `exit_code: 0` → success (stderr may still contain warnings)
   - `exit_code: non-zero` → failure, analyze
   - `signal: not null` → process was killed, analyze signal
   - `exit_code: null` (no exit, still running) → shouldn't happen, flag

2. **Exit code interpretation**
   - Match against known patterns for the command
   - Generic codes: 1 (general error), 2 (misuse), 126 (not executable), 127 (command not found), 137 (SIGKILL = OOM)
   - Command-specific: parse output for known error patterns of that tool

3. **Signal interpretation**
   - SIGTERM → killed by timeout_watcher (time limit)
   - SIGKILL → force-killed after SIGTERM failed, or OOM killer
   - SIGSEGV → command crashed (native code bug, not our problem)
   - SIGPIPE → tried to write to a closed pipe (probably benign)

4. **Error extraction**
   - Scan stderr for error patterns: `error:`, `Error:`, `ERROR:`, `fatal:`, `panic:`, `Traceback`
   - Extract the most specific error message (last line of a traceback, first line of a one-liner)
   - Detect common failure modes:
     - `command not found` → tool not installed
     - `permission denied` → sandbox too restrictive
     - `no such file` → path doesn't exist in sandbox
     - `out of memory` → resource limit hit
     - `connection refused` → network restricted
     - `syntax error` → command malformed

5. **Build suggestion**
   - Recoverable errors → provide fix suggestion
   - Non-recoverable errors → explain why it can't be fixed automatically
   - Unknown errors → report raw exit + stderr summary, flag for human analysis

## Failure Modes
| Condition | Response |
|---|---|
| Unknown exit code (tool-specific) | Report `exit_code` + last 3 lines of stderr, flag as unknown |
| stderr is empty but exit_code != 0 | Diagnosis: `"command failed silently"`, flag as hard-to-diagnose |
| stdout contains error indicators but exit 0 | Flag as `"possible soft failure"`, report suspicious stdout lines |
| Mixed languages in error output | Parse each, report all, note language ambiguity |
