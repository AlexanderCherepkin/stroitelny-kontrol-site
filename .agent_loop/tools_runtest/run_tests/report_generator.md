# Report Generator

## Role
Produces a comprehensive, human-readable test report from structured results. The single source of truth for "how did the tests go?" — from a one-line summary to a full CI-ready report.

## Contract
- **Receives**: `{ results: { summary, failures, coverage, flaky }, format: "summary"|"detailed"|"ci"|"markdown", options: { include_passing, include_skipped, max_failure_detail } }`
- **Returns**: `{ report: string, metadata: { format, generated_at, summary_stats } }`
- **Side effects**: none (pure formatting)

## Decision Flow

1. **Summary format** (one-liner or short block)
   - Header: `Tests: N passed, M failed, K skipped, J errored in X.Xs`
   - If all pass: single success line, green
   - If failures: failure count + worst failure headline
   - Coverage: `Coverage: 82% lines, 75% branches`
   - Flaky: `Flaky: 3 tests detected (login_test, api_test, cache_test)`

2. **Detailed format** (per-test breakdown)
   - Section: Failures first (most important)
     - Each failure: test name, file location, error message, stack trace (truncated to `max_failure_detail`)
     - Sorted by: category severity or execution order
   - Section: Errors (infrastructure failures)
   - Section: Skipped (with skip reason if available)
   - Section: Passing (if `include_passing: true`, summary line otherwise)

3. **CI format** (GitHub Actions / GitLab CI compatible)
   - Use annotations syntax: `::error file={path},line={line}::{message}`
   - Exit code: non-zero if any failure
   - Machine-parseable summary line for dashboard
   - Link to full log / coverage report if available

4. **Markdown format** (for PRs, issues, chat)
   - Heading hierarchy: `## Test Results`, `### Failures`, `### Coverage`
   - Code blocks for error messages and stack traces
   - Emoji status indicators: ✅ pass, ❌ fail, ⚠️ flaky, ⏭️ skip
   - Collapsible details for long stack traces (`<details>` tags)

5. **Cross-cutting additions**
   - Flaky test warning at top (even when they passed this run)
   - Coverage delta vs last run
   - Link to fix_suggestor output if failures exist
   - Timestamp + commit hash header

## Failure Modes
| Condition | Response |
|---|---|
| Results object is empty | Report: "No test results available" |
| Report exceeds max output size | Truncate per-failure detail, keep summary |
| Mixed framework results in one report | Label sections by framework |
