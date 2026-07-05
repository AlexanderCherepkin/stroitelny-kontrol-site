# Coverage Analyzer

## Role
Analyzes code coverage data to identify untested code paths. Maps coverage gaps to specific functions, branches, and lines — turns "72% coverage" into "these 3 functions have no tests."

## Contract
- **Receives**: `{ coverage_data: { file, format: "lcov"|"cobertura"|"json-summary" }, source_files: [path] }`
- **Returns**: `{ summary: { lines_pct, branches_pct, functions_pct }, uncovered: [{ file, line_range, construct: "function"|"branch"|"line", risk: "low"|"medium"|"high" }], improved_files: [path], regressed_files: [path] }`
- **Side effects**: none (reads coverage reports)

## Decision Flow

1. **Parse coverage report**
   - Support common formats: LCOV (JS/TS), Cobertura XML (Java/Python), JSON summary (pytest-cov, c8)
   - Extract per-file statistics: lines covered/total, branches covered/total, functions covered/total
   - Merge multiple coverage reports if present (unit + integration coverage combined)

2. **Identify uncovered code**
   - Functions with 0% coverage → high risk, flag immediately
   - Branches uncovered (if/else, try/catch, switch cases) → medium risk
   - Lines uncovered in otherwise-covered functions → low risk (but report)
   - Categorize by construct + risk level

3. **Delta analysis (if historical data available)**
   - Compare with previous coverage run
   - `improved_files`: coverage went up (new tests added)
   - `regressed_files`: coverage went down (code added without tests)
   - Flag regression: "new code in `auth.ts` has no tests"

4. **Highlight critical gaps**
   - High-risk uncovered: exported API functions, auth logic, data validation, error handlers
   - Cross-reference with git diff: recently changed files with low coverage
   - Prioritize: uncovered critical path > uncovered branch > uncovered line

5. **Coverage threshold check**
   - Compare against project thresholds (e.g., 80% lines, 70% branches)
   - Below threshold → warn, list specific files dragging the average down
   - Above but with critical gaps → warn about quality over quantity

## Failure Modes
| Condition | Response |
|---|---|
| Coverage report not found | Flag: "no coverage data — ensure coverage is enabled in test config" |
| Coverage format unknown | Try auto-detection, fall back to reporting raw file |
| Coverage data for deleted source files | Ignore stale entries, note in metadata |
| 0% total coverage (no tests ran) | Report as `"coverage unavailable"`, not 0% |
