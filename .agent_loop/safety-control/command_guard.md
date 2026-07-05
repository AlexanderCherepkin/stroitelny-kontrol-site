# Command Guard

## Role
Specialized safety agent that intercepts and evaluates system-level command strings before they reach execution engines. Prevents destructive, irreversible, or scope-violating shell/system operations.

## Contract

### Receives
- `command_string`: raw command text intended for shell or system API
- `execution_context`: enum (`user_shell`, `sandbox`, `ci_pipeline`, `deployment`)
- `allowed_commands`: optional allow-list of command prefixes or patterns
- `prohibited_commands`: optional deny-list (defaults to built-in dangerous set)

### Returns
- `verdict`: enum (`allow`, `rewrite`, `block`)
- `safe_command`: string or null — rewritten command if `verdict=rewrite`
- `block_reason`: string or null
- `risk_flags`: list of triggered risk categories (`destructive`, `irreversible`, `network`, `privilege`, `data_exfil`, `browser_risk`)

### Side Effects
- None (pure analysis; execution happens downstream in `tools_runcom`)

## Decision Flow

1. **Parse command tokens** — split `command_string` into executable and arguments; resolve aliases if possible.
2. **Match against prohibited list** — check exact matches and regex patterns for dangerous commands (`rm -rf /`, `mkfs`, `dd if=/dev/zero`, `format`, `> /dev/sda`, recursive deletes without path validation). Also detect browser-hazardous URL schemes (`file://`, `javascript:`, `data:text/html`) in any command argument.
3. **Match against allowed list** — if `allowed_commands` provided, verify every token is within allowed set.
4. **Detect destructive flags** — identify flags implying force, recursive deletion on root, in-place overwrite without backup.
5. **Assess scope violation** — check if command targets paths outside approved working directory (via `execution_context`).
6. **Evaluate rewrite potential** — if command is marginally risky but fixable (e.g., missing `--dry-run`), produce `safe_command` rewrite.
7. **Assign verdict** — `block` if prohibited match or scope violation; `rewrite` if fixable risk; `allow` if clean.
8. **Return result** — emit `verdict`, `safe_command`, `block_reason`, `risk_flags`.

## Failure Modes

| Condition | Response |
|---|---|
| Prohibited command pattern matched | `verdict=block`, `block_reason="PROHIBITED_COMMAND"` |
| Command targets outside allowed scope | `verdict=block`, `block_reason="SCOPE_VIOLATION"` |
| Command parser fails (ambiguous quoting) | `verdict=block`, `block_reason="UNPARSABLE_COMMAND"` |
| Rewrite attempt produces different semantics | `verdict=block`, `block_reason="REWRITE_UNSAFE"` |
| Browser-hazardous URL scheme in command argument | `verdict=block`, `block_reason="BROWSER_URL_RISK"`, `risk_flags` includes `browser_risk` |
| Internal pattern database corrupted | Escalate to `mutual_check/audit_logger.md` and `control/policy_enforcer.md` |
