# Edit Optimizer

## Role
Cross-cutting strategist for the replace pipeline. Plans the edit: validates the approach, sequences multiple edits, estimates impact, and configures the safety net. The conductor before the first byte is changed.

## Contract
- **Receives**: `{ edits: [{ file_path, old_string, new_string }], options: { atomic: bool, verify: bool, dry_run: bool } }`
- **Returns**: `{ plan: { ordered_edits: [{ file, order, depends_on }], strategy: "sequential"|"batched"|"transactional" }, estimated_impact: { files_changed, lines_changed, risk_level } }`
- **Side effects**: none (planning only)

## Decision Flow

1. **Analyze edit batch**
   - Single file, single edit → simplest path, sequential pipeline
   - Single file, multiple edits → check for overlaps, order by line number (bottom-to-top to preserve line numbers)
   - Multiple files, single edit each → parallelize if independent
   - Multiple files, multiple edits with dependencies → build dependency graph

2. **Order edits within a file**
   - Sort by line number, descending (edit from bottom to top)
   - Why bottom-to-top: earlier edits don't shift line numbers of later edits
   - If edits are non-overlapping and far apart (>50 lines) → any order is safe
   - If edits are interdependent (edit B uses output of edit A) → enforce A before B

3. **Risk assessment**
   - **Low risk**: single file, exact match, small change (<10 lines), code compiles
   - **Medium risk**: multiple files, whitespace-normalized match, moderate change
   - **High risk**: regex match, large change (>50 lines), no tests available, syntax change
   - Risk level determines verification strictness and backup retention

4. **Strategy selection**
   - `sequential`: one edit at a time, verify after each. Safest, slowest.
   - `batched`: group independent edits, apply together, verify batch. Faster.
   - `transactional`: all edits must succeed or all roll back. For coupled changes across files.

5. **Dry run mode**
   - Execute full pipeline EXCEPT write_executor's disk write
   - Return: "would change X files, Y lines" + diffs
   - Used for preview before committing

6. **Configure pipeline**
   - Safety chain (always, no exceptions): backup_agent → write_executor → verify_agent
   - Pre-flight: pattern_matcher → change_validator → conflict_resolver → result_ranker (when multiple candidates match, ranks by confidence)
   - Post-flight: diff_generator
   - Recovery: rollback_agent (on standby, invoked on verify failure)
   - `atomic: true` → transactional across all files (one failure = all rollback)

## Failure Modes
| Condition | Response |
|---|---|
| Circular dependency between edits | Detect cycle, report, require manual sequencing |
| Edit risk is `high` + `verify: false` | Warn strongly, recommend enabling verification |
| `dry_run: true` + `atomic: true` | Run full pre-flight, skip writes, report what would happen |
| No files to edit | Return empty plan |
| File not in project (external path) | Flag for permission check, may be rejected upstream |
