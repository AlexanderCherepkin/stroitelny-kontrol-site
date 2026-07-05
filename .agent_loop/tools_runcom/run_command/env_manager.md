# Env Manager

## Role
Sets up the environment variables for command execution. Ensures the command sees exactly the environment it needs — no leaked secrets, no inherited sensitive vars, no pollution.

## Contract
- **Receives**: `{ command, env_strategy: "clean"|"inherit"|"merge", env_vars: { key: value }, secrets: [key] }`
- **Returns**: `{ environment: { key: value }, redacted_environment: { key: "***"|value }, env_hash }`
- **Side effects**: none (prepares env, doesn't execute)

## Decision Flow

1. **Select base environment**
   - `clean`: empty environment + explicitly provided vars only. Safest, most predictable.
   - `inherit`: copy current process environment. Fastest, risk of secret leakage.
   - `merge` (default): start with clean, add essential system vars (PATH, HOME, TEMP, LANG), add user-provided vars. Best balance.

2. **Essential vars (merge mode)**
   - Always include: `PATH`, `HOME`, `TEMP`/`TMPDIR`, `LANG`, `TERM`
   - Always exclude: `AWS_*`, `GITHUB_TOKEN`, `NPM_TOKEN`, `DOCKER_*`, `KUBECONFIG`, `SSH_AUTH_SOCK`, `.env` contents
   - Platform-specific: `SystemRoot` (Windows), `LD_LIBRARY_PATH` (Linux)

3. **Apply user vars**
   - Override defaults with `env_vars` provided
   - Validate var names (no shell metacharacters, valid identifiers)
   - Validate var values (no injection patterns)

4. **Secret handling**
   - If a secret is needed by the command → inject via env var, not command line
   - After execution: scrub from environment, do NOT log
   - Generate `redacted_environment` for logging (secrets replaced with `***`)
   - Secrets never appear in `env_hash` computation

5. **Compute env hash**
   - Hash of all non-secret env vars for reproducibility tracking
   - Same env hash → same environment → comparable results

## Failure Modes
| Condition | Response |
|---|---|
| Required env var missing (command needs it) | Warn, let it fail naturally or provide default |
| Sensitive var detected in `inherit` mode | Redact it, warn: `"$SECRET leaked from parent env"` |
| Var value contains injection pattern | Reject, sanitize, suggest alternative |
| Env size exceeds OS limit | Warn (very rare, >32KB of env vars) |
