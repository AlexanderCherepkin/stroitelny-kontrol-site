# Diff Generator

## Role
Generates a clean, readable diff of the edit. Shows exactly what changed — the delta between before and after. Used by both the pipeline (for logging/audit) and the user (for review/confirmation).

## Contract
- **Receives**: `{ file_path, backup_id, new_content_hash, options: { format: "unified"|"side-by-side"|"minimal", context_lines: int } }`
- **Returns**: `{ diff: string, stats: { lines_added, lines_removed, hunks }, file_path }`
- **Side effects**: none (read-only, reads backup and current file)

## Decision Flow

1. **Load sources**
   - Load original content from backup (by backup_id)
   - Load current content from file on disk
   - Verify hashes match expected values before diffing

2. **Generate hunk-level diff**
   - Line-by-line comparison (Myers diff algorithm)
   - Group changed regions into hunks with context
   - Each hunk: `@@ -old_start,old_count +new_start,new_count @@` header
   - Lines starting with `-` (removed), `+` (added), space (context)

3. **Format output**
   - `unified`: standard `---` / `+++` header + hunk blocks. Default for automation.
   - `side-by-side`: `old │ new` two-column format. Best for human review.
   - `minimal`: only changed lines, no context. Compactest form.

4. **Apply formatting heuristics**
   - If edit is within a function → include the function signature in context (even if outside context_lines)
   - If edit is in a Markdown file → include the nearest heading as section marker
   - Collapse unchanged runs longer than 10 lines into `... (N unchanged lines)`

5. **Return**
   - Full diff string
   - Statistics for summary reporting
   - Ready for display or audit logging

## Failure Modes
| Condition | Response |
|---|---|
| Backup not found by ID | Return error, cannot generate diff |
| Current file hash doesn't match expected | Warn that diff may not reflect the intended edit |
| Files are identical (no change) | Return empty diff + `stats: { lines_added: 0, lines_removed: 0 }` |
| Diff exceeds max output size | Truncate to first N hunks, flag `truncated` |
