# File Context

## Role
File-system observation agent that tracks all file-level mutations performed during execution. Maintains a precise, reversible map of which files were read, created, modified, renamed, or deleted, enabling accurate rollback and precise result reporting.

## Contract

### Receives
- `execution_trace`: from `execution/action_logging.md`
- `pre_execution_file_index`: snapshot of file system state before execution
- `observation_scope`: enum (`targeted`, `workspace`, `recursive`) — how widely to scan for changes
- `include_content`: boolean — whether to capture diffs or just metadata

### Returns
- `file_changes`: list of change records with path, change type, old hash, new hash, and size delta
- `diff_artifacts`: list of unified diffs or content snapshots if `include_content=true`
- `orphaned_references`: list of paths referenced in plan but not found or modified unexpectedly
- `integrity_check`: enum (`passed`, `failed`, `partial`) — whether observed changes match expected changes

### Side Effects
- Writes diff artifacts to temporary storage for rollback
- Updates file watch index in session memory

## Decision Flow

1. **Determine scan scope** — `targeted` checks only paths mentioned in `execution_trace`; `workspace` scans project root; `recursive` scans entire subtree.
2. **Take post-execution snapshot** — stat all files in scope; capture hashes, sizes, timestamps, permissions.
3. **Compare with pre-index** — compute symmetric difference to identify created, modified, deleted, and renamed files.
4. **Resolve renames** — detect moved files by hash match if path changed but content identical.
5. **Generate diffs** — if `include_content=true`, compute unified diff for each modified file; store full content for each created file.
6. **Validate against expectations** — compare observed changes against `execution_trace` predicted changes; flag discrepancies.
7. **Check orphaned references** — identify paths the plan expected to read or modify but were not touched or found.
8. **Compute integrity** — `passed` if all expected changes occurred and no unexpected changes; `failed` if unexpected changes or missing expected changes; `partial` if minor deviations.
9. **Return** — emit changes, diffs, orphaned references, integrity check.

## Failure Modes

| Condition | Response |
|---|---|
| Pre-execution index missing | Reconstruct from version control or last known snapshot; `integrity_check=partial` |
| File read fails mid-scan (race with deletion) | Mark as deleted in post-snapshot; note race condition in `file_changes` |
| Diff computation exceeds memory for huge file | Generate hash-based summary only; `include_content=false` for that file; log truncation |
| Unexpected binary file modification | Include binary hash delta; skip text diff; flag as `integrity_check=partial` |
| Workspace root inaccessible during scan | Return partial results for accessible subtrees; flag inaccessible paths |
