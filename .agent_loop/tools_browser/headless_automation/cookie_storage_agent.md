# Browser Cookie Storage Agent

## Role
Manages cookies, localStorage, and sessionStorage within an ephemeral browser context under privacy and scope rules.

## Contract

### Receives
- `session_handle`: from `session_manager.md`
- `operation`: enum (`get`, `set`, `delete`, `clear`, `list`)
- `storage_type`: enum (`cookies`, `local_storage`, `session_storage`)
- `key`: key name for `get`/`set`/`delete`
- `value`: value for `set`
- `domain`: optional domain filter for cookies

### Returns
- `operation_status`: enum (`success`, `blocked`, `error`)
- `data`: retrieved values (for `get`/`list`)
- `redacted`: boolean — whether sensitive values were masked

### Side effects
- Reads or mutates browser storage
- Logs operation to `audit_logger.md`

## Decision Flow

1. **Resolve session and context** — return error if invalid.
2. **Check policy** — reject `set`/`clear` unless domain is in trusted list or operation is explicitly scoped.
3. **Execute operation**:
   - `cookies`: use `context.cookies()` / `context.add_cookies()` / `context.clear_cookies()`;
   - `local_storage`/`session_storage`: evaluate JS in page context.
4. **Redact sensitive values** — mask tokens, passwords, session IDs in returned data.
5. **Return** — emit status, data, and redaction flag.

## Failure Modes

| Condition | Response |
|---|---|
| Attempt to set cross-domain cookies | `operation_status=blocked`; route to `control/network_guard.md` |
| Storage contains unredactable secrets | `operation_status=blocked`; do not return raw values |
| Clear all storage without approval | `operation_status=blocked`; require `execution/human_approval.md` |
| JS evaluation error in storage access | `operation_status=error`; log to `error_handler.md` |
| Session context already disposed | `operation_status=error`; request new session |
