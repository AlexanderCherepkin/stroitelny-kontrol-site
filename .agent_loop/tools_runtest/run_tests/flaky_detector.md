# Flaky Detector

## Role
Identifies flaky tests — tests that pass and fail intermittently without code changes. A test that fails 1/10 times destroys trust in the suite. Detection is the first step toward fixing.

## Contract
- **Receives**: `{ test_history: [{ test_name, status, timestamp, commit_hash }], options: { min_runs: int, flaky_threshold: 0..1 } }`
- **Returns**: `{ flaky_tests: [{ test_name, flake_rate, pattern: "always-pass-then-fail"|"random"|"environment-dependent"|"ordering-dependent", last_10_results }], summary }`
- **Side effects**: none (reads test history)

## Decision Flow

1. **Ingest test history**
   - Load from test run database / CI history
   - Filter to same commit hash (code didn't change) OR recent N runs
   - Require `min_runs` (default: 5) — can't detect flaky with 1 run
   - Each entry: test name, status, timestamp, run duration

2. **Compute flake rate**
   - For each test: `failures / total_runs`
   - `flaky_threshold` (default: 0.1 = 10% failure rate) → flaky
   - But NOT 100% failure rate (that's just a broken test, not flaky)
   - And NOT 0% failure rate (that's stable)
   - Flaky: 0.1 < fail_rate < 0.9

3. **Classify flaky pattern**
   - `always-pass-then-fail`: passes N times, then fails once. Async race condition, resource leak.
   - `random`: no temporal pattern. Likely: random data, time-based, external dependency.
   - `environment-dependent`: fails on CI, passes locally. Missing env var, network, filesystem diff.
   - `ordering-dependent`: passes alone, fails in full suite. Shared state between tests.

4. **Evidence collection**
   - Show last 10 results for each flaky test
   - Compare passing vs failing durations (slow runs → likely timeout-bound flaky)
   - Compare failure error messages across runs (same error → reproducible, different → environmental)

5. **Severity ranking**
   - Sort by flake rate descending
   - Highest priority: high flake rate + runs often (wastes most CI time)
   - Flag tests that recently became flaky (was stable, now not)

## Failure Modes
| Condition | Response |
|---|---|
| Insufficient history (< min_runs) | Flag: "not enough data to detect flakiness" |
| All tests are 100% pass or 100% fail | Report: no flaky tests detected (may be true or data is insufficient) |
| Test renamed between runs | Match by file+line if name differs, flag identity uncertainty |
| History DB corrupted | Partial analysis, flag data quality issue |
