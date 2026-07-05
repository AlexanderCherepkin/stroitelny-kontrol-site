# Ponytail Audit

## Role
Repository-wide over-engineering auditor. Scans the whole codebase (not just a diff) and ranks the biggest opportunities to delete, shrink, or replace code with stdlib/native/existing solutions.

## Contract

### Receives
- `workspace_root`: string — absolute or relative path to the repository root.
- `scope`: string — `all`, `src`, `generated`, or `runtime`. Default `all`.
- `ponytail_mode`: string | None — `lite`, `full`, `ultra`, or `off`. Defaults from env/session state.
- `max_findings`: int — cap on returned findings (default 50).

### Returns
- `findings`: list[dict] — ranked findings with `rank`, `file`, `tag`, `what_to_cut`, `replacement`, `estimated_lines_saved`.
- `net_lines_removable`: int — total estimated removable lines.
- `dependencies_removable`: list[string] — package/dependency names that could be removed.
- `summary`: string — `Lean already. Ship.` if nothing found, otherwise top-line summary.

### Side effects
- Reads the repository tree; does not write or delete files.
- Logs audit scope and result count to `audit_logger.md`.

## Decision Flow

1. **Short-circuit if disabled** — if `ponytail_mode` is `off`, return summary `Ponytail disabled.` and empty findings.
2. **Resolve scope** — default to `all`; validate against allowed values; fall back to `all` on invalid input.
3. **Build file list** — walk `workspace_root` excluding `node_modules`, `.git`, `build`, `dist`, `.next`, `coverage`, `.venv`, `__pycache__`, `.tmp`, `.logs`.
4. **Apply scope filter** — if `src`, restrict to `src/`, `app/`, `lib/`, `components/`; if `generated`, restrict to generated output directories; if `runtime`, restrict to `runtime/` and `mcp_servers/`.
5. **Scan files** — read text files and look for patterns matching each tag:
   - `delete` — unused imports, dead functions, commented-out blocks, unreachable exports, speculative feature flags.
   - `stdlib` — custom implementations of stdlib utilities (sort, date parsing, string padding, etc.).
   - `native` — dependencies doing what the browser/platform provides (date pickers, simple modals, clipboard, fetch wrappers).
   - `yagni` — abstractions with one implementation, config objects that never vary, single-use interfaces.
   - `shrink` — verbose code that collapses to a clearer equivalent.
   - `reuse` — duplicated helper logic across files.
6. **Rank findings** — by `estimated_lines_saved` descending; cap at `max_findings`.
7. **Estimate dependencies** — collect external packages only used by `delete`/`native`/`stdlib` findings.
8. **Return report** — findings, totals, dependency list, and summary. No file mutations.

## Failure Modes

| Condition | Response |
|---|---|
| `workspace_root` unreadable | Return one error finding and `summary=Audit failed: workspace unreadable` |
| Scan exceeds timeout budget | Return partial findings with `truncated=true`; log timeout |
| No findings | `summary=Lean already. Ship.` |
| Invalid scope value | Fall back to `all`; log warning |
| Binary or large files | Skip; record in `skipped_files` metadata |
