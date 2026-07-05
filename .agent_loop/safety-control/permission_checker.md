# Permission Checker

## Role
Authorization gate that validates whether the requested action is allowed for the current identity, context, and resource. Enforces least-privilege principle before any tool execution.

## Contract

### Receives
- `identity`: caller identifier (user_id, agent_id, or session_token)
- `action`: enum (`read`, `write`, `execute`, `delete`, `network`, `database`, `admin`)
- `target_resource`: path, URL, or resource descriptor being acted upon
- `context_tags`: optional list of runtime tags (e.g., `preview_mode`, `sandbox`)

### Returns
- `decision`: enum (`allow`, `deny`, `escalate`)
- `allowed_scope`: subset of requested scope that is permitted, or null
- `deny_reason`: string or null
- `audit_token`: unique traceable ID for this permission check

### Side Effects
- Writes permission decision to audit log
- Increments per-identity rate-limit counter if configured

## Decision Flow

1. **Resolve identity** — map `identity` to roles/groups via identity provider; fail closed if unresolvable.
2. **Load policy rules** — fetch applicable policy set for (`identity`, `action`, `target_resource`, `context_tags`).
3. **Evaluate explicit deny** — check deny-list first; if match, return `deny` immediately.
4. **Evaluate allow rules** — check allow-list and role-based permissions; compute maximal allowed scope.
5. **Check contextual overrides** — apply `context_tags` (sandbox may expand, preview_mode may restrict).
6. **Check rate limits** — if identity exceeds per-action quota, downgrade to `deny` or `escalate`.
7. **Determine decision** — if requested scope ⊆ `allowed_scope`, return `allow`; if partial overlap, return `allow` with reduced `allowed_scope`; if no overlap, return `deny`.
8. **Log and return** — generate `audit_token`, log decision, return result.

## Failure Modes

| Condition | Response |
|---|---|
| Identity cannot be resolved | `decision=deny`, `deny_reason="UNKNOWN_IDENTITY"` |
| Policy store unreachable | `decision=escalate`, `deny_reason="POLICY_UNAVAILABLE"`, trigger `mutual_check/compliance_checker.md` |
| Rule conflict (allow vs deny for same scope) | `decision=deny`, `deny_reason="POLICY_CONFLICT"`, escalate to `human_oversight.md` |
| Rate limit exceeded | `decision=deny`, `deny_reason="RATE_LIMIT"` |
| Target resource descriptor malformed | `decision=deny`, `deny_reason="INVALID_RESOURCE"` |
