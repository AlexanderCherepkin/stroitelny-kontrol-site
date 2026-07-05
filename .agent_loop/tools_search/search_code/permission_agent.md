# Permission Agent

## Role
Validates that the search operation stays within allowed boundaries. Mirrors `tools_read/permission_agent` but specialised for search: directory traversal is broader than single-file read, so the risk surface is larger.

## Contract
- **Receives**: `{ scope: { roots, include_globs, exclude_globs }, operation: "read"|"traverse" }`
- **Returns**: `{ allowed: bool, reason: string, effective_scope: { roots, include_globs, exclude_globs } }`
- **Side effects**: none (reads policy config only)

## Decision Flow

1. **Root boundary check**
   - Every root must be inside an allowed directory
   - If any root is outside → deny immediately (no partial approval)
   - Symlinks in root paths must resolve within boundaries

2. **Traversal depth check**
   - Set max directory depth (default: 20) — prevents runaway recursion
   - If scope includes broad pattern (`**`) without depth limit → enforce max depth

3. **Exclusion enforcement**
   - Ensure deny-listed patterns are ALWAYS in exclude_globs
   - Merge project-wide deny list into exclude set (`.env*`, `*.key`, `credentials.*`, `secrets.*`)
   - Exclusion list is additive — user can add more, cannot remove defaults

4. **Include restriction**
   - If user attempts to include a restricted path → strip it from include_globs, warn
   - Restricted paths: system directories, paths outside project, permission-denied directories

5. **Return effective scope**
   - Cleaned and validated scope object
   - May be smaller than requested (paths stripped due to restrictions)
   - If everything was stripped → deny with reason

## Failure Modes
| Condition | Response |
|---|---|
| Root outside allowed boundaries | Deny + `"path {x} is outside sandbox"` |
| All include paths were restricted | Deny + list of stripped paths |
| Excessive depth request (>100) | Cap at max, warn |
| No readable files in scope after filtering | Allow but warn `"scope is empty after permission filtering"` |
| Policy unreadable | Deny (fail closed) |
