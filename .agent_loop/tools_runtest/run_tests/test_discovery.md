# Test Discovery

## Role
Finds all tests in the project. Scans the codebase for test files, test functions, and test suites. Without discovery, the pipeline doesn't know what to run.

## Contract
- **Receives**: `{ scope: { paths, patterns }, test_frameworks: ["auto-detect"|"jest"|"pytest"|"go test"|...] }`
- **Returns**: `{ suites: [{ name, file, framework, test_count_estimate, tags }], total_suites, total_tests_estimate }`
- **Side effects**: none (read-only scan)

## Decision Flow

1. **Detect frameworks**
   - `auto-detect`: look for config files (`jest.config.*`, `pytest.ini`, `go.mod`, `Cargo.toml`, `phpunit.xml`)
   - Check dependencies (`package.json`, `requirements.txt`, `pom.xml`)
   - Detect multiple frameworks → support all, label each suite with framework
   - Unknown framework → flag, attempt generic test pattern matching

2. **Find test files by convention**
   - `*.test.{ts,tsx,js,jsx}` → Jest/Vitest
   - `test_*.py`, `*_test.py` → pytest/unittest
   - `*_test.go` → Go testing
   - `*Test.java`, `*Tests.java` → JUnit
   - `*_spec.rb` → RSpec
   - `*.test.{rs}` → Cargo test
   - Custom patterns from project config override conventions

3. **Parse test structure**
   - For each test file: scan for test functions/methods
   - Detect: `test()`, `it()`, `describe()` (JS), `def test_` (Python), `func Test` (Go), `@Test` (Java)
   - Count tests per file, per suite
   - Extract test names and any tags/categories

4. **Categorize**
   - Tag suites: `unit`, `integration`, `e2e`, `slow`, `fast`, `flaky`
   - Read tags from: directory structure (`tests/unit/`, `__tests__/integration/`), annotations/decorators, naming
   - Identify dependencies between suites (integration tests need unit tests to pass first)

## Failure Modes
| Condition | Response |
|---|---|
| No tests found | Return empty, suggest creating a test file with framework template |
| Framework detected but config broken | Report which config file has issues |
| Test file parsing fails (syntax error in test) | Flag broken test file, continue scanning other files |
| Mixed frameworks in one project | Support all, label each, warn about potential conflicts |
| 0 test functions found in test files | Warn: "test files exist but contain no test functions" |
