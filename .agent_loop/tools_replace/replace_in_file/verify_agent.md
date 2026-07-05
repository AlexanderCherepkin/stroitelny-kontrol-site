# Verify Agent

## Role
Post-write validation. Independently verifies that the edit produced correct, working code. The final quality gate — catches what change_validator couldn't predict and what write_executor might have missed.

## Contract
- **Receives**: `{ file_path, original_hash, new_hash, edit_description, verification_checks: ["compile"|"lint"|"test"|"integration"] }`
- **Returns**: `{ verified: bool, checks: [{ check, passed, output }], summary }`
- **Side effects**: may run compiler/linter/test process (read-only except for build artifacts)

## Decision Flow

1. **Content integrity**
   - Read file, compute hash → must match `new_hash` from write_executor
   - Verify old_string is gone and new_string is in place
   - Check that unintended changes didn't leak in (diff between backup and current)
   - Verify file encoding is preserved

2. **Syntax/structure re-check**
   - Parse the full file (not just the changed region)
   - Does the complete file still parse correctly?
   - Are bracket pairs balanced across the whole file?
   - No orphaned references (import of deleted symbol, call to removed function)

3. **Compile check (if applicable)**
   - If project has a build step: run it on just this file if possible, or full project
   - Compilation error that didn't exist before → blocking failure
   - Warning that didn't exist before → advisory

4. **Lint check (if applicable)**
   - Run linter on changed file
   - New lint errors → advisory (not blocking, but reported)
   - If edit was specifically to fix a lint error → verify that error is gone

5. **Test check (if requested)**
   - Run tests related to the changed file
   - Tests that passed before must still pass
   - If edit adds new functionality and no tests exist → flag, not block

6. **Aggregate verdict**
   - All checks pass → `verified: true`
   - Compile/test failure → `verified: false`, preserve backup for rollback
   - Lint/style only → `verified: true` with recommendations

## Failure Modes
| Condition | Response |
|---|---|
| Build system not available | Skip compile check, flag as unverified |
| Tests not found for changed file | Skip test check, note coverage gap |
| Verification times out (>30s) | Return partial results, flag as incomplete |
| Post-edit hash mismatch | Critical — possible disk corruption, restore from backup |
