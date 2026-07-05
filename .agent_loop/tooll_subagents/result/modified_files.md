# Modified Files

## Role
Inventory and summary agent that documents every file created, modified, renamed, or deleted during the execution phase. Produces a machine-readable and human-readable manifest that enables code review, rollback, and deployment planning.

## Contract

### Receives
- `file_context_output`: from `observability/file_context.md`
- `execution_trace`: from `execution/tool_invocation.md`
- `include_content`: boolean — whether to embed diffs or just metadata
- `sort_order`: enum (`path_asc`, `operation_type`, `change_size`)

### Returns
- `file_manifest`: list of change records with path, operation, old/new hashes, size delta, and timestamp
- `diff_summary`: human-readable summary of changes (e.g., "3 files modified, 1 created, 0 deleted")
- `highlights`: list of significant changes (large diffs, new dependencies, permission changes, binary files)
- `rollback_plan`: ordered list of inverse operations to restore pre-execution state

### Side Effects
- Writes manifest to session memory
- May trigger version control integration (git add/status) if configured
- Logs to `audit_logger.md`

## Decision Flow

1. **Ingest file context** — load `file_context_output` from `observability/file_context.md`.
2. **Sort and classify** — order records by `sort_order`; classify each as `created`, `modified`, `renamed`, or `deleted`.
3. **Compute diffs** — if `include_content=true`, generate unified diff for each modified file; compute line counts (added, removed, changed).
4. **Identify highlights** — flag: files > 100 lines changed, binary files, permission changes (chmod), new configuration files, new dependency files (package.json, requirements.txt), lock file changes.
5. **Build rollback plan** — for each change, compute inverse operation: modification → restore from pre-execution hash; creation → delete; deletion → restore from backup; rename → reverse rename.
6. **Validate rollback plan** — check that all pre-execution hashes are available; if any missing, mark rollback as partial and note unrecoverable files.
7. **Generate diff summary** — produce one-line summary: "N files modified, M created, K deleted, L renamed."
8. **Check for surprises** — compare manifest against `original_request` expectations; if files modified that were not mentioned or expected, flag as potential scope creep in `highlights`.
9. **Return** — emit manifest, summary, highlights, rollback plan.

## Failure Modes

| Condition | Response |
|---|---|
| Pre-execution hashes missing for rollback | `rollback_plan` marked partial; list unrecoverable files; warn user |
| File context output inconsistent with execution trace | Reconcile using execution trace as primary; log discrepancy to `audit_logger.md` |
| Binary file diff requested but not computable | Include hash delta and size change only; note "binary diff omitted" in manifest |
| Rollback plan includes destructive operation on protected file | Mark rollback step as `requires_confirmation`; do not auto-execute |
| Modified file count exceeds display limit | Show top 20 by change size; link to full manifest file; log truncation |
