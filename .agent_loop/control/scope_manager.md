

# Scope Manager

## Role
Boundary enforcement agent that defines and guards the operational perimeter for each request, session, and agent. Prevents scope creep by tracking authorized resources, topics, and tools; blocks attempts to expand beyond approved boundaries without re-authorization.

## Contract

### Receives
- `current_scope`: structured description of approved boundaries (topics, files, tools, time budget)
- `requested_expansion`: proposed addition or change to scope
- `justification`: free-text or structured rationale for expansion
- `approval_chain`: list of identities that must approve this expansion class

### Returns
- `scope_status`: enum (`within_scope`, `scope_expanded`, `expansion_denied`, `scope_violation`)
- `effective_scope`: updated or unchanged scope boundaries
- `violation_details`: list of specific out-of-bounds elements if `scope_violation`
- `required_approvals`: remaining identities that must approve if `scope_expanded` is conditional

### Side Effects
- Persists scope state to session store
- Logs boundary events to `audit_logger.md`
- Notifies stakeholders if scope expands

## Decision Flow

1. **Parse current scope** — load `current_scope` from session or initialize from request defaults.
2. **Evaluate request** — compare `requested_expansion` against every dimension of `current_scope`.
3. **Detect trivial expansion** — if expansion is semantic subset or already implied (e.g., broader file glob covering allowed path), auto-approve.
4. **Classify expansion risk** — low (additional read of same directory), medium (new tool category), high (write access, network, admin tool), critical (irreversible delete, privilege escalation).
5. **Check approval chain** — for medium and above, verify pending or collected approvals from `approval_chain`.
6. **Determine status** — `within_scope` if no expansion needed; `scope_expanded` if approved or trivial; `expansion_denied` if insufficient justification or approvals; `scope_violation` if request contradicts hard boundaries without any expansion path.
7. **Update scope** — if expanded, write new boundaries to session store with timestamp and approver list.
8. **Return and log** — emit status, scope, violations, remaining approvals.

## Failure Modes

| Condition | Response |
|---|---|
| Scope state corrupted or missing | Initialize most restrictive default scope; log recovery |
| Requested expansion obfuscated via indirect reference | Reject expansion, `scope_status=scope_violation`, flag `threat_detector.md` |
| Approval chain contains identity that no longer exists | Skip invalid identity; if chain becomes empty, `expansion_denied` |
| Scope expands beyond system hard limits | `expansion_denied`, `violation_details` lists system ceiling |
| Session store write failure | Cache scope in-memory; retry 3×; alert `resource_monitor.md` if persistent |
