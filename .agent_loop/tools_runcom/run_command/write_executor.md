# Write Executor

## Role
Handles command outputs that write to the filesystem. When a command produces files (build artifacts, generated code, logs), Write Executor captures, validates, and registers them. Also handles writing input scripts for commands that need them.

## Contract
- **Receives**: `{ operation: "capture"|"write_script"|"cleanup", targets: [{ path, content|source, expected_hash }] }`
- **Returns**: `{ results: [{ path, success, hash, bytes_written|bytes_captured }], summary }`
- **Side effects**: WRITES TO / READS FROM FILESYSTEM (inside sandbox)

## Decision Flow

1. **capture mode** — collect command-generated files
   - After command execution: scan expected output paths
   - For each file found: read, hash, record metadata
   - For each file expected but missing → flag
   - For files found but not expected → flag (command had undocumented side effects)
   - Move files from sandbox temp to persistent storage

2. **write_script mode** — prepare scripts for execution
   - When command is complex (heredoc, inline script) → write to temp file first
   - Set executable permissions
   - Verify script was written correctly (hash check)
   - Return path for executor_agent to invoke

3. **cleanup mode** — remove temporary files
   - After successful execution: delete temp scripts, intermediate files
   - After failed execution: preserve temp files for debugging
   - Never delete expected output artifacts
   - Track what was cleaned up vs preserved

4. **Validation**
   - After write: read back, verify hash
   - After capture: verify file is complete (no truncation)
   - Check file permissions are appropriate (no world-writable configs)

## Failure Modes
| Condition | Response |
|---|---|
| Expected output file not found after command | Flag, suggest command may have failed silently |
| Unexpected output file found | Report path and content preview, flag for review |
| Script write fails (disk full, permissions) | Abort, do not execute partial script |
| Hash mismatch after write | Delete corrupt file, retry once, then abort |
| Cleanup fails to remove temp files | Leave them, flag for manual cleanup |
