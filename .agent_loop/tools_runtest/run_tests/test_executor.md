# Test Executor

## Role
Executes tests by delegating to the appropriate test framework. Bridges test_planner's plan with run_command's execution engine. One executor, many frameworks.

## Contract
- **Receives**: `{ batch: { suites, framework }, options: { timeout_ms, retry_count, env_vars } }`
- **Returns**: `{ results: [{ suite, test_name, status: "pass"|"fail"|"skip"|"error", duration_ms, output }], summary: { passed, failed, skipped, errored, total_duration_ms } }`
- **Side effects**: SPAWNS TEST PROCESSES (delegates to run_command pipeline)

## Decision Flow

1. **Build framework-specific command**
   - Jest: `npx jest --json --outputFile=result.json <file>`
   - pytest: `python -m pytest --json-report -q <file>`
   - Go: `go test -json ./...`
   - Cargo: `cargo test -- --format json`
   - PHPUnit: `phpunit --log-json=result.json <file>`
   - Use JSON output whenever possible (structured, parsable)

2. **Execute via run_command pipeline**
   - Delegate to `command_builder → sandbox_agent → env_manager → timeout_watcher → executor_agent → output_collector`
   - Set env vars for test run (DB URLs, API keys for test environment)
   - Test timeout = sum of individual test timeouts + overhead
   - Capture both structured output (JSON) and raw output (for fallback parsing)

3. **Parse structured output**
   - Extract individual test results: name, status, duration, error message, stack trace
   - Map framework statuses to unified statuses: pass/fail/skip/error
   - Capture console output per test (debug logs, warnings)

4. **Handle framework crashes**
   - Framework exits with error (not test failure) → mark all tests in batch as `error`
   - Framework produces no output → timeout or crash, capture raw stderr
   - Framework produces unparseable output → delegate to log_parser for raw parsing

5. **Retry logic**
   - `retry_count > 0` → retry failed tests individually
   - Retry with same configuration, fresh process
   - Track retry history per test (first: fail, second: pass → flaky signal)

## Failure Modes
| Condition | Response |
|---|---|
| Framework not installed | Report missing dependency with install command |
| Test process killed by timeout | Mark running tests as `error`, report timeout |
| JSON output unparseable | Fall back to log_parser for regex-based parsing |
| No tests in batch | Return empty results (normal — filter may have excluded everything) |
| Framework version incompatible | Detect version, report compatibility issue |
