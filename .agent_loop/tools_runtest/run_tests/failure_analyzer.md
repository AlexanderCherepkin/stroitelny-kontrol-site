# Failure Analyzer

## Role
Diagnoses test failures. Translates "test_login failed" into "AssertionError: expected 200, got 401 — auth token expired". The bridge between a red result and an actionable fix.

## Contract
- **Receives**: `{ failures: [{ test_name, error_message, stack_trace, code_context }] }`
- **Returns**: `{ diagnoses: [{ test_name, root_cause: string, category: string, file_location, suggested_investigation }] }`
- **Side effects**: none (pure analysis)

## Decision Flow

1. **Categorize failure**
   - **Assertion error**: test expected X, got Y. Logic bug or outdated test.
   - **Null/undefined error**: something wasn't initialized, mocked, or provided.
   - **Timeout**: test hung. Async deadlock, missing await, infinite loop.
   - **Import/Module error**: dependency missing, path wrong, circular import.
   - **API/Network error**: connection refused, 404, 500. Service unavailable or URL wrong.
   - **Type error**: wrong type passed. Interface mismatch, schema change.
   - **Compile/Syntax error**: test file itself is broken.
   - **Resource error**: file not found, permission denied, disk full.

2. **Extract root cause**
   - Parse stack trace → find the deepest frame in user code (not framework, not node_modules)
   - That frame's file + line + function → primary investigation point
   - Read the assertion message: "expected X, got Y" → what's the gap?
   - For comparison failures: compute diff between expected and actual

3. **Locate in codebase**
   - `file_location`: file + line from stack trace top user-code frame
   - Also locate: the function under test, the assertion site
   - Cross-reference with recent git changes (did this test fail because code changed?)

4. **Build investigation suggestion**
   - Category-specific leading questions:
     - Assertion: "Did the expected behavior change, or is the test outdated?"
     - Null/undefined: "Is the dependency being mocked correctly?"
     - Timeout: "Is there an unhandled promise or missing await?"
     - API: "Is the service running? Has the endpoint URL changed?"
   - Point to specific line(s) to investigate

## Failure Modes
| Condition | Response |
|---|---|
| Stack trace empty | Flag as `"no stack trace available"`, rely on error message only |
| Error message unparseable | Report raw error, `category: "unknown"` |
| Multiple root causes in one test | Report the first (triggering) failure, note others |
| Failure caused by test infrastructure (not code) | Distinguish: "test env issue" vs "code issue" |
