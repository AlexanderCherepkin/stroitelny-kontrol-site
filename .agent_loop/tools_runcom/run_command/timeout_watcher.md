# Timeout Watcher

## Role
Enforces time limits on command execution. Every command gets a deadline — no process runs forever. Kills runaway processes and cleans up orphaned children.

## Contract
- **Receives**: `{ command, timeout_ms, options: { kill_signal: "SIGTERM"|"SIGKILL", graceful_period_ms, warn_at_percent: [50, 80, 95] } }`
- **Returns**: `{ started_at, deadline, timed_out: bool, actual_runtime_ms, kill_escalated: bool }`
- **Side effects**: may send kill signals to child processes (destructive — prevents resource exhaustion)

## Decision Flow

1. **Set timeout**
   - Use provided `timeout_ms`
   - If not provided: infer from command_builder's `estimated_runtime_ms` × 3 (safety margin)
   - If still unknown: default 120000ms (2 minutes)
   - Store `started_at` and `deadline` timestamps

2. **Monitor execution**
   - Track wall-clock time since process start
   - At each `warn_at_percent` threshold → emit warning with elapsed time
   - Warning at 50%: informational
   - Warning at 80%: "command approaching timeout"
   - Warning at 95%: "command about to be killed"

3. **Graceful termination (timeout reached)**
   - Send `kill_signal` (default: SIGTERM)
   - Wait `graceful_period_ms` (default: 5000ms) for process to exit cleanly
   - Process exits in this window → `timed_out: true`, no escalation
   - Process still running → escalate to SIGKILL (force kill)

4. **Force kill escalation**
   - Send SIGKILL (or platform equivalent: `taskkill /F` on Windows)
   - Kill entire process group (children too, no orphans)
   - Record: `kill_escalated: true`
   - Verify process tree is actually dead

5. **Cleanup**
   - Reap zombie processes
   - Release file descriptors held by process
   - Return runtime + timeout status

## Failure Modes
| Condition | Response |
|---|---|
| Process won't die even with SIGKILL | Critical — stuck in kernel I/O. Flag for manual intervention. |
| Timeout set to 0 (infinite) | Reject: no command runs forever |
| Timeout set unreasonably high (>1 hour) | Warn, but respect it |
| Child processes orphaned (process group incomplete) | Scan and kill by parent PID, warn if any were missed |
| Platform doesn't support process groups | Kill only the direct child, log warning |
