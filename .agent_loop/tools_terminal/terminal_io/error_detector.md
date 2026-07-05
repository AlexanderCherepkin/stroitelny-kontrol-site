# Error Detector

## Role
Detects errors in terminal output. Scans both structured error codes and unstructured text for failure signals. "Command finished" means nothing — "command finished with exit code 1 and 'permission denied'" means everything.

## Contract
- **Receives**: `{ output: string, exit_code: int, context: { command, shell_type } }`
- **Returns**: `{ errors: [{ type: string, message: string, severity: "info"|"warning"|"error"|"fatal", location: { line, column } }], has_errors: bool }`
- **Side effects**: none (pure detection)

## Decision Flow

1. **Exit code analysis**
   - 0 → no error (but check stderr for warnings)
   - 1 → general error, scan output for specifics
   - 2 → misuse (wrong arguments, invalid syntax)
   - 126 → not executable (permissions)
   - 127 → command not found
   - 128+N → killed by signal N (130 = Ctrl+C, 137 = SIGKILL/OOM)
   - Non-standard codes → report raw code + scan output

2. **Scan output for error patterns**
   - Shell errors: "command not found", "permission denied", "no such file", "is a directory"
   - Process errors: "Segmentation fault", "Killed", "Out of memory", "Aborted"
   - Git errors: "fatal:", "error:", "CONFLICT", "not a git repository"
   - Docker errors: "Error response from daemon", "Cannot connect"
   - Package manager errors: "ERR!", "npm ERR!", "ERROR:", "Could not find"
   - Generic: "error", "failed", "traceback", "panic", "fatal"

3. **Severity classification**
   - `fatal`: process killed, cannot continue. SIGKILL, OOM, segfault.
   - `error`: command failed. Non-zero exit, explicit error message.
   - `warning`: command succeeded but had issues. Warnings, deprecation notices.
   - `info`: noteworthy but not problematic. Skipped steps, optional features missing.

4. **Multi-error handling**
   - Compiler output: many errors → group by file, count per file
   - Linter output: many warnings → categorize by rule, count per rule
   - Test output: many failures → summarize (delegate to failure_analyzer in tools_runtest)

5. **Context-aware detection**
   - "error" in npm audit output = real vulnerability
   - "error" in log output = might be a log level label, not actual error
   - Check: is this just the word "error" in normal output, or an actual failure?
   - Heuristic: error keyword + non-zero exit = actual error; error keyword + exit 0 = likely label

## Failure Modes
| Condition | Response |
|---|---|
| Output language is non-English | Use exit code as primary signal, try generic patterns |
| Error output interleaved with normal output | Parse line-by-line, classify each |
| Exit code 0 but output contains fatal patterns | Flag: "possible undetected failure" |
| Multiple conflicting error signals | Report all, flag ambiguity |
