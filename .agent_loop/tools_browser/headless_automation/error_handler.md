# Browser Error Handler

## Role
Central classifier for browser automation failures. Decides whether an error is transient, fatal, or safety-related and triggers the appropriate cleanup or escalation.

## Contract

### Receives
- `error_type`: enum (`navigation`, `timeout`, `crash`, `selector`, `network`, `permission`, `unknown`)
- `error_message`: raw error string
- `session_handle`: from `session_manager.md`
- `current_url`: URL at failure time

### Returns
- `classification`: enum (`transient`, `fatal`, `safety`, `resource`)
- `retry_allowed`: boolean
- `cleanup_required`: boolean
- `escalation_target`: agent path or null
- `user_message`: sanitized explanation

### Side effects
- May trigger `browser_close` cleanup
- Logs failure to `audit_logger.md`
- May route to `control/human_oversight.md` for safety events

## Decision Flow

1. **Normalize error** — map Playwright error classes to `error_type`.
2. **Classify**:
   - `navigation` + timeout → `transient`, `retry_allowed=true`;
   - `crash` / browser disconnected → `fatal`, `cleanup_required=true`;
   - `permission` / file access denial → `safety`, escalate to `control/file_system_guard.md`;
   - `network` / proxy failure → `transient` if retry budget remains;
   - `selector` not found → `transient` if page still loading;
   - unknown → `fatal` if repeats twice.
3. **Sanitize message** — remove local file paths, tokens, and internal stack traces from `user_message`.
4. **Decide cleanup** — `cleanup_required=true` for fatal/crash/safety errors.
5. **Return** — emit classification, retry/cleanup flags, escalation target, and sanitized message.

## Failure Modes

| Condition | Response |
|---|---|
| Error message contains secrets | Strip before logging; route to `data_leak_preventer.md` |
| Browser crash during cleanup | Log remaining state; mark session as dead |
| Same error repeats more than 3 times | Reclassify as `fatal`; stop retrying |
| Safety-related error with no escalation path | Default to `control/human_oversight.md` |
