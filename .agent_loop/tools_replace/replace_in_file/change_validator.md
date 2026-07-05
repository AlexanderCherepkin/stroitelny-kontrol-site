# Change Validator

## Role
Pre-flight safety check. Validates the proposed change BEFORE it touches disk. Catches: syntax errors, type violations, style regressions, security concerns, and structural damage. The last line of defense before bytes are committed.

## Contract
- **Receives**: `{ file_path, old_string, new_string, file_type, validation_rules: ["syntax"|"style"|"security"|"structure"|"custom"] }`
- **Returns**: `{ valid: bool, checks: [{ rule, passed, severity, message }], blocking_issues: int }`
- **Side effects**: none (pure analysis, no disk writes)

## Decision Flow

1. **Syntax validation**
   - If file is code: parse `new_string` in the context of the file's language
   - Does the new text compile/parse without errors?
   - Check: balanced brackets, unclosed strings, valid identifiers
   - If old_string was syntactically valid and new_string isn't → blocking issue

2. **Structure validation**
   - Does the edit break indentation consistency? (new_string indentation vs surrounding code)
   - Does it preserve paired constructs? (opening/closing tags, brackets, fences)
   - Does it maintain the file's encoding? (no mixed encodings introduced)

3. **Security scan**
   - New string introduces: hardcoded credentials, SQL injection patterns, eval() calls, innerHTML, shell exec?
   - New string removes: auth checks, input validation, error handling?
   - Severity: any security issue → blocking

4. **Style consistency**
   - Does new_string match the file's prevailing style? (quotes, semicolons, line endings, naming convention)
   - Non-blocking: style mismatch is advisory, not a hard stop

5. **Custom rules (project-specific)**
   - Load from project config (`.agent_loop/validation_rules/`)
   - Examples: "no console.log in production code", "all API routes must have auth middleware"
   - Unknown custom rules → skip, don't fail

6. **Aggregate verdict**
   - All blocking checks pass → `valid: true`
   - Any blocking check fails → `valid: false` + list of issues
   - Only advisory issues → `valid: true` with warnings

## Failure Modes
| Condition | Response |
|---|---|
| Language unknown (can't parse) | Skip syntax check, run structure + security only |
| New string is empty (deletion) | Validate structure after deletion (no orphaned references) |
| File type detection fails | Run all non-language-specific checks |
| Validation rules conflict | Report conflict, let caller resolve |
| Security check times out (complex analysis) | Time out after 500ms, flag as unvalidated (not blocking) |
