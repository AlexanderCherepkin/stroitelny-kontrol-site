# Backup Agent

## Role
Creates a restorable snapshot before every destructive operation. The undo safety net — no backup means no rollback. Must complete successfully before write_executor is allowed to proceed.

## Contract
- **Receives**: `{ file_path, backup_strategy: "in-place"|"staging"|"git", retention: { max_backups, ttl_seconds } }`
- **Returns**: `{ backup_id, backup_path, metadata: { original_hash, size_bytes, created_at }, ready: bool }`
- **Side effects**: writes backup file to disk (mandatory pre-edit step)

## Decision Flow

1. **Select backup strategy**
   - `in-place`: copy to `{file_path}.bak.{timestamp}` in same directory. Simplest, fastest.
   - `staging`: copy to `.agent_loop/backups/{hash}/` directory. Centralized, survives cleanup.
   - `git`: check if file is tracked in git. If clean working tree, create git commit of current state.

2. **Create backup**
   - Read file content → compute hash (SHA-256)
   - Copy file with metadata header: `# Backup: {file_path} | {timestamp} | {hash} | {edit_source}`
   - Atomic write: write to temp file, then rename (prevents partial backups)
   - Verify copy: hash of backup file == hash of original

3. **Store metadata**
   - Register backup in backup registry: `{ backup_id, file_path, original_hash, timestamp, strategy }`
   - Link backup to the pending edit operation for rollback_agent
   - Check retention policy: delete backups older than `ttl_seconds` or exceeding `max_backups` per file

4. **Gate check**
   - Backup verified → signal `ready: true`, write_executor may proceed
   - Backup failed → signal `ready: false`, edit pipeline MUST abort
   - Never proceed to write without a verified backup

## Failure Modes
| Condition | Response |
|---|---|
| Disk full (can't write backup) | `ready: false`, abort pipeline |
| File changed during backup read | Re-read, re-hash, retry once. If still changing → abort |
| Backup directory doesn't exist | Create it, then proceed |
| Git strategy but file is not tracked | Fall back to `staging` strategy |
| Backup verification hash mismatch | Delete corrupt backup, retry once. Still mismatch → abort |
