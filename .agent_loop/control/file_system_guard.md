# File System Guard

## Role
Runtime enforcement agent that confines all file operations to approved directories, prevents path traversal, enforces read/write/execute permissions per identity, and blocks unauthorized access to sensitive system paths.

## Contract

### Receives
- `operation`: enum (`read`, `write`, `delete`, `execute`, `list`, `move`)
- `target_path`: absolute or relative path requested
- `identity`: agent or user requesting the operation
- `context`: enum (`sandbox`, `user_workspace`, `system_temp`, `restricted`)

### Returns
- `permission`: enum (`granted`, `denied`, `read_only`, `sandbox_only`)
- `resolved_path`: canonical absolute path after resolution
- `restriction_reason`: string or null
- `audit_reference`: traceable ID for this access decision

### Side Effects
- Logs access attempt to `audit_logger.md`
- Updates file access telemetry

## Decision Flow

1. **Resolve path** — canonicalize `target_path` against current working directory; reject if resolution fails.
2. **Detect traversal** — check for `..` sequences, symlink chains, or null-byte injection that escape approved roots.
3. **Map to context root** — determine allowed root based on `context`: `sandbox` → isolated temp; `user_workspace` → project directory; `system_temp` → OS temp; `restricted` → explicit allow-list only.
4. **Check identity permissions** — lookup identity ACL for `operation` on resolved path prefix.
5. **Evaluate special paths** — block access to `/etc`, `/sys`, registry hives, SSH keys, browser profiles regardless of context unless explicit admin override.
6. **Determine permission** — `granted` if all checks pass; `denied` if traversal or unauthorized path; `read_only` if write blocked but read allowed; `sandbox_only` if operation allowed only in ephemeral temp.
7. **Log and return** — emit decision, canonical path, reason, audit ID.

## Failure Modes

| Condition | Response |
|---|---|
| Path resolution ambiguous (symlink cycle) | `permission=denied`, `restriction_reason="AMBIGUOUS_PATH"` |
| Context root not configured | `permission=denied`, `restriction_reason="MISSING_CONTEXT_ROOT"` |
| Identity ACL store unreachable | `permission=denied` for non-sandbox; `sandbox_only` for sandbox with warning |
| Admin override present but expired | Reject override, `permission=denied`, escalate to `human_oversight.md` |
| Race condition during path canonicalization | Retry once with file-lock; if still racing, `permission=denied` |
| Asset download plan targets outside `public/` | `permission=denied` unless explicitly approved by `tooll_subagents/planning/asset_agent.md` and logged to `audit_logger.md` |
| Image enrichment download targets outside `public/assets/enriched/` | `permission=denied` unless explicitly approved by `tooll_subagents/planning/image_enrichment_agent.md` and logged to `audit_logger.md` |
