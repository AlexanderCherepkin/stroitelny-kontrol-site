



# Write Planner

## Role
Plans the execution strategy for commands that will modify the filesystem. Coordinates with backup_agent and write_executor from tools_replace to ensure every destructive command has a safety net.

## Contract
- **Receives**: `{ command, expected_side_effects: { files_modified: [path], files_created: [path], files_deleted: [path] }, options: { requires_backup, atomic } }`
- **Returns**: `{ plan: { pre_backups: [{ file, backup_id }], execution_order: [step], post_verification: [check], rollback_commands: [command] } }`
- **Side effects**: none (planning only, actual backups are orchestrated via tools_replace)

## Decision Flow

1. **Classify side effects**
   - Read-only command (`ls`, `cat`, `grep`, `git log`) → no backup needed, minimal planning
   - File modification (`sed -i`, `echo >>`, `touch`) → backup affected files
   - File creation (`cp`, `mkdir`, `npm init`) → check for overwrites
   - File deletion (`rm`, `mv`, `git clean`) → backup BEFORE delete
   - Unknown side effects → assume worst case, backup related files

2. **Build execution order**
   - Pre-backup step: delegate to `tools_replace/backup_agent` for each affected file
   - Command execution step: the main command
   - Verification step: did the command do what was expected?
   - Known-safe commands may skip backup (configurable via `requires_backup`)

3. **Build rollback plan**
   - For each file to be modified: corresponding restore command
   - Order: reverse of execution order
   - If command creates files → rollback deletes them
   - If command deletes files → rollback restores from backup
   - Rollback commands must be safe (no `rm -rf` in rollback)

4. **Atomicity**
   - `atomic: true` → all changes must succeed or all roll back
   - If any verification step fails → execute full rollback plan
   - Non-atomic → each step independently verified, partial success allowed

## Failure Modes
| Condition | Response |
|---|---|
| Side effects unknown (opaque command) | Flag as high-risk, require full backup of affected directories |
| Rollback command is missing (no way to undo) | Flag, require human approval before proceeding |
| Affected file list is huge (>100 files) | Warn, suggest narrower command scope |
| Pre-backup fails for any file | Abort entire plan, do not execute command |
