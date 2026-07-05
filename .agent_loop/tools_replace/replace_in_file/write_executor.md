









# Write Executor

## Role
Performs the actual file modification. The only agent in the pipeline that writes to disk. Executes the replacement and confirms the bytes landed correctly.

## Contract
- **Receives**: `{ file_path, old_string, new_string, match: { line_start, line_end }, backup_id, options: { atomic: bool, create_if_missing: bool } }`
- **Returns**: `{ success: bool, bytes_written, new_hash, write_time_ms }`
- **Side effects**: MODIFIES FILE ON DISK (destructive — guarded by backup_agent)

## Decision Flow

1. **Pre-flight checks**
   - `backup_id` must be present and verified (refuse to write without backup)
   - Re-read file, verify content still matches expected `old_string` (no external changes since pattern_matcher ran)
   - Lock file for write (exclusive lock) to prevent concurrent modifications

2. **Execute replacement**
   - Load file content
   - Replace `old_string` with `new_string` at the matched position
   - If `match_mode: "all"` was used → replace all occurrences
   - Preserve file encoding (BOM, line endings, final newline)

3. **Write strategy**
   - `atomic: true` (default): write to temp file in same directory, fsync, rename over original
   - `atomic: false`: direct overwrite (faster, but partial write on crash = corruption)
   - Atomic is strongly preferred for all code/config files

4. **Post-write verification**
   - Read back the file
   - Hash the new content
   - Verify `new_string` exists at the expected position
   - Verify `old_string` no longer exists (unless it was a non-unique pattern with multiple occurrences)
   - Verify file size changed by expected delta (`len(new) - len(old)`)

5. **Return result**
   - All checks pass → `success: true`
   - Any check fails → attempt rollback via rollback_agent, return `success: false`

## Failure Modes
| Condition | Response |
|---|---|
| No backup_id provided | REFUSE to write (hard block) |
| File changed externally since match | Abort, report diff, require re-match |
| Disk write fails (permissions, IO error) | Abort, do NOT leave temp file |
| Post-write verification fails | Restore from backup immediately, report failure |
| File encoding changes unintentionally | Restore from backup, report encoding drift |
| Write to missing file without `create_if_missing` | Abort, suggest using file creation agent instead |
