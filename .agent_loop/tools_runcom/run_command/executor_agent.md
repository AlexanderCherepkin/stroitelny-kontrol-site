# Executor Agent

## Role
Spawns and manages the child process. The actual fork+exec — turns a sanitized command string and prepared environment into a running process. Bridges the gap between planning and output.

## Contract
- **Receives**: `{ command, environment, sandbox_id, timeout_ms, working_dir }`
- **Returns**: `{ pid, exit_code, signal: string|null, runtime_ms, stdin_bytes_written }`
- **Side effects**: SPAWNS CHILD PROCESS (OS-level, in sandbox)

## Decision Flow

1. **Pre-execution checks**
   - `sandbox_id` must be present and `ready: true`
   - `command` must be non-empty, passed through command_builder validation
   - `timeout_ms` must be set (no infinite execution)
   - `working_dir` must exist inside sandbox

2. **Spawn process**
   - Create process inside sandbox
   - Attach stdin pipe (write side), stdout pipe (read side), stderr pipe (read side)
   - Set environment from env_manager output
   - Set process group ID (for timeout_watcher's kill escalation)
   - Record PID and start time

3. **Feed stdin (optional)**
   - If command expects stdin input → write it, close stdin pipe
   - Max stdin size: 1MB
   - Binary stdin → base64 before piping

4. **Stream output**
   - stdout and stderr stream to output_collector (non-blocking)
   - Don't buffer all output in memory — large output kills context
   - Pipe to output_collector in chunks

5. **Wait for completion**
   - Block with timeout → timeout_watcher may interrupt
   - Capture: exit_code, signal (if killed), elapsed wall-clock time
   - If process was killed → `signal: "SIGTERM"` or `"SIGKILL"`

6. **Post-execution**
   - Verify process exited (not zombie)
   - Close all pipes
   - Return execution metadata to caller

## Failure Modes
| Condition | Response |
|---|---|
| Process fails to spawn (exec error) | Return `exit_code: -1` + spawn error message |
| Stdin write fails (pipe broken) | Close stdin, continue (command may not need it) |
| Sandbox not ready | Refuse to spawn, propagate sandbox error |
| Working directory missing | Refuse to spawn, suggest correction |
| Process exited before output_collector attached | Normal for fast commands, capture buffered output |
