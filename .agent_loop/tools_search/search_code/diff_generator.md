# Diff Generator

## Role
Generates diffs between file versions or between search result and current state. Shows what changed — the delta between expectation and reality.

## Contract
- **Receives**: `{ base: { file, content|commit|branch }, target: { file, content|commit|branch }, options: { context_lines, format: "unified"|"side-by-side"|"git" } }`
- **Returns**: `{ diff: string, stats: { additions, deletions, files_changed }, hunks: [{ header, lines }] }`
- **Side effects**: none (read-only, may call git)

## Decision Flow

1. **Resolve comparison sources**
   - `file vs file`: read both, diff directly
   - `file vs commit`: git show commit:path, diff against current
   - `commit vs commit`: git diff X..Y
   - `branch vs branch`: git diff branchA..branchB
   - `content vs content`: inline string comparison (no filesystem)

2. **Generate diff**
   - Line-by-line comparison (Myers diff algorithm)
   - Group changed lines into hunks
   - Each hunk has a header: `@@ -old_start,old_count +new_start,new_count @@`
   - Context lines: unchanged lines surrounding changes (default: 3)

3. **Format output**
   - `unified`: standard diff format with +/- prefixes
   - `git`: unified with git-style headers (`diff --git a/... b/...`)
   - `side-by-side`: two-column format (`old │ new`), best for human reading

4. **Annotate**
   - `additions`: count of lines added
   - `deletions`: count of lines removed
   - `files_changed`: number of distinct files in diff
   - `hunks`: array of individual change blocks for programmatic processing

5. **Apply size limits**
   - If diff exceeds max output size → truncate to first N hunks, flag `truncated`
   - If file count > 50 → summarize per-file stats, show full diff for first 10

## Failure Modes
| Condition | Response |
|---|---|
| File not found in one version | Show entire file as addition or deletion |
| Binary files compared | Show `"binary files differ"`, no inline diff |
| Empty diff (identical content) | Return empty diff with `stats: { additions: 0, deletions: 0 }` |
| Git command failed | Fall back to direct file comparison if possible |
| Diff too large (>100K lines) | Truncate with summary stats |
