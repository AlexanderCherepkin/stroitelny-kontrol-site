# Log Parser

## Role
Parses raw test output into structured results when structured output is unavailable. The fallback that ensures no test result is lost — regex-driven extraction from framework text output.

## Contract
- **Receives**: `{ raw_output: string, framework: string, output_format: "text"|"mixed" }`
- **Returns**: `{ results: [{ test_name, status, duration_ms, error_message, stack_trace }], parse_quality: "full"|"partial"|"minimal" }`
- **Side effects**: none (pure parsing)

## Decision Flow

1. **Select parser by framework**
   - Jest (text): parse lines — `✓ test name (N ms)` → pass, `✕ test name (N ms)` → fail, `○ test name` → skip
   - pytest (verbose): `PASSED`, `FAILED`, `SKIPPED`, `ERROR` markers + `::` separator for test path
   - Go test: `--- PASS: TestName`, `--- FAIL: TestName`, `ok/fail` module lines
   - Cargo test: `test name ... ok`, `test name ... FAILED`
   - Generic fallback: search for `PASS`, `FAIL`, `ERROR`, `OK`, `ok` markers

2. **Extract test metadata**
   - Test name: from marker line
   - Duration: extract time value near status marker (ms or s)
   - Status: normalize to pass/fail/skip/error
   - Error message + stack trace: capture lines between FAIL marker and next test/end marker
   - Module/suite name: from file header or path separator

3. **Handle edge cases**
   - Test with no output (empty) → skip in results, note
   - Interleaved parallel test output → sort by test name, group lines
   - ANSI escape codes → strip before parsing
   - Multi-line test names → join, preserve

4. **Assess parse quality**
   - `full`: all test names + statuses extracted, durations parsed, errors intact
   - `partial`: most extracted but some lines unparseable
   - `minimal`: only pass/fail counts from summary line

## Failure Modes
| Condition | Response |
|---|---|
| Raw output is empty | Return empty results, `parse_quality: "minimal"` |
| Framework unknown (no parser) | Use generic parser, `parse_quality: "minimal"`, flag |
| Mixed output (JSON fragments in text) | Extract JSON blocks, text-parse the rest, merge |
| Output in non-English locale | Detect locale, try English fallback patterns |
| Truncated output (log cut off mid-test) | Parse what's available, flag `"output truncated"` |
