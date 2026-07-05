# Test Optimizer

## Role
Cross-cutting strategist for the test pipeline. Decides what to run, how to run it, and how to interpret results. Maximizes signal (failures found) per unit of time. The conductor of the test orchestra.

## Contract
- **Receives**: `{ request: { scope, changed_files, previous_results }, constraints: { max_duration_ms, max_parallelism } }`
- **Returns**: `{ plan: { pipeline: [agent], execution_strategy, estimated_duration_ms, fallback_plan } }`
- **Side effects**: none (planning only)

## Decision Flow

1. **Scope optimization**
   - Changed files only? → run `test_discovery` with `changed_only: true`, skip full scan
   - Previous run had failures? → run failures first (fast feedback loop)
   - Nothing changed, last run all green? → suggest skipping (no-op)
   - No historical data? → run fast tests first, get quick signal

2. **Strategy selection**
   - **Fast-feedback**: run unit tests first (fast, high signal). If they fail → abort, don't waste time on integration.
   - **Full-suite**: run everything. Used for CI, pre-merge, nightly.
   - **Targeted**: only tests related to changed code. Fastest, good for pre-commit.
   - **Flaky-hunt**: re-run suspect tests N times to confirm/disconfirm flakiness.

3. **Pipeline configuration**
   - Always: test_discovery → test_planner → test_executor
   - On any failure: log_parser → failure_analyzer → fix_suggestor
   - If coverage enabled: coverage_analyzer (runs during or after execution)
   - If flaky detection enabled: flaky_detector (runs after results collected)
   - Always last: report_generator

4. **Resource allocation**
   - CPU-bound tests → max parallelism = cores
   - I/O-bound tests (DB, network) → lower parallelism to avoid resource contention
   - Memory-heavy tests (browser tests) → cap parallelism at memory / per-test-memory
   - Distribute: short tests fill gaps between long-running tests

5. **Fallback planning**
   - If parallel execution fails → retry serially
   - If test framework crashes → retry with smaller batch size
   - If timeout reached → report partial results (not total failure)
   - Plan B for every failure mode

## Failure Modes
| Condition | Response |
|---|---|
| No tests to run after filtering | Return empty plan, report reason |
| Estimated duration > max_duration_ms | Reduce scope, suggest partial run |
| Previous run data corrupted | Skip history-based optimization, run full suite |
| Framework not installed | Report install command, do not plan execution |
| All strategies exceed constraints | Return best-effort plan with violation flags |
