# Test Planner

## Role
Decides which tests to run, in what order, with what concurrency. Transforms "run tests" into a precise execution plan that respects dependencies and time constraints.

## Contract
- **Receives**: `{ suites, options: { filter: { tags, files, names, changed_only }, order: "fast-first"|"failures-first"|"dependency", parallel: int, timeout_per_suite_ms } }`
- **Returns**: `{ plan: { batches: [{ suites: [name], estimated_time_ms }], total_estimated_time_ms, parallel_groups } }`
- **Side effects**: none (planning only)

## Decision Flow

1. **Filter tests**
   - `tags: ["unit"]` → only unit tests
   - `files: ["auth_test.py"]` → specific files
   - `names: ["test_login"]` → specific test cases by name
   - `changed_only: true` → only tests related to changed files (git diff)
   - No filters → run everything
   - Intersection of all filters (AND logic)

2. **Order tests**
   - `fast-first`: sort by estimated runtime ascending. Fast feedback on failures.
   - `failures-first`: run previously failing tests first. Verify fixes immediately.
   - `dependency`: topological sort. Unit → integration → e2e. Dependent suites wait.
   - Default: fast-first within each dependency tier.

3. **Parallelisation**
   - Unit tests → high parallelism (4-8x, no shared state)
   - Integration tests → moderate parallelism (2-4x, shared DB/containers)
   - E2E tests → low parallelism (1-2x, browser resources)
   - Respect framework's parallelism capabilities (Jest workers, pytest-xdist, etc.)
   - Cap: never exceed available CPU cores × 2

4. **Batch assignment**
   - Group tests by framework (can't mix Jest and pytest in one run)
   - Within framework: assign to parallel batches
   - Each batch: list of suites, estimated time, resource needs
   - Batch total time = max(suite times), not sum (they run in parallel)

5. **Timeline estimate**
   - Sum batch times → `total_estimated_time_ms`
   - If > timeout → adjust: reduce parallelism or drop optional suites
   - Attach to each suite: estimated time from historical runs (test_discovery baseline)

## Failure Modes
| Condition | Response |
|---|---|
| Filter eliminates ALL tests | Warn, return empty plan |
| Dependency cycle detected (A depends on B, B depends on A) | Break cycle by running both, warn about dependency issue |
| Estimated time exceeds timeout | Suggest: reduce scope, increase parallelism, or increase timeout |
| No historical timing data | Use conservative defaults: 100ms per test unit, 500ms per integration |
