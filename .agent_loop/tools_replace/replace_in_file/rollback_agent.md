# Rollback Agent

## Role
Restores files to their pre-edit state. The emergency undo — invoked when verification fails, when the user rejects a change, or when downstream effects cascade. Every edit must be reversible.

## Contract
- **Receives**: `{ backup_id, reason: string, options: { cleanup_backup: bool, notify: bool } }`
- **Returns**: `{ restored: bool, restored_hash, verification: { hash_matches_original: bool } }`
- **Side effects**: RESTORES FILE TO PREVIOUS STATE (destructive — overwrites current with backup)

## Decision Flow

1. **Locate backup**
   - Find backup by `backup_id` in backup registry
   - Verify backup file exists and is readable
   - Verify backup hash matches registry record (backup not corrupted)

2. **Pre-rollback snapshot**
   - Create a temporary snapshot of current (broken) state before restoring
   - Label as `pre-rollback-{backup_id}` for post-mortem analysis
   - This is NOT a backup — just forensic evidence of what went wrong

3. **Execute restore**
   - Copy backup content over current file
   - Use atomic write (temp + rename) to prevent partial restore
   - Set file mtime to backup's original mtime (preserve timestamp)
   - Restore original file permissions if they were captured

4. **Verify restore**
   - Read restored file, compute hash
   - Compare against backup's original hash
   - Must match exactly → `restored: true`
   - Mismatch → retry once, then escalate

5. **Cleanup**
   - `cleanup_backup: true` → delete backup file + registry entry (edit permanently accepted)
   - `cleanup_backup: false` → keep backup (user may want to re-apply or inspect)
   - Delete pre-rollback forensic snapshot if restore was clean

6. **Notify**
   - Log rollback event: `{ file, backup_id, reason, restored_hash, timestamp }`
   - If `notify: true` → signal upstream that an edit was reversed

## Failure Modes
| Condition | Response |
|---|---|
| Backup not found | Critical failure — report unrecoverable, preserve current state |
| Backup corrupted (hash mismatch) | Report dual failure: both edit and backup are bad |
| Restore verification hash mismatch | Retry once, then report partial failure |
| File locked by another process | Wait 500ms, retry. Still locked → report, do not force |
| Multiple rollback requests for same edit | Idempotent — second rollback is a no-op (already restored) |
