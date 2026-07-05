# Quota Manager

## Role
Resource governance agent that enforces limits on compute, memory, API calls, tokens, and storage per identity, session, or layer. Prevents resource exhaustion, cost overruns, and denial-of-service via consumption.

## Contract

### Receives
- `resource_request`: descriptor of requested resources (CPU ms, tokens, API calls, storage bytes)
- `quota_identity`: identifier for limit scope (user, session, agent, or system-wide)
- `quota_policy_id`: active policy defining limits and burst allowances
- `priority_level`: enum (`critical`, `normal`, `background`, `best_effort`)

### Returns
- `quota_decision`: enum (`granted`, `granted_partial`, `denied`, `delayed`)
- `allocated_resources`: actual resources approved
- `remaining_quota`: resources still available after this allocation
- `reset_time`: timestamp when quota bucket refreshes
- `throttle_factor`: float (1.0 = full speed, lower = throttled)

### Side Effects
- Atomically decrements quota counters
- Queues `delayed` requests for later admission
- Logs all decisions to `audit_logger.md`

## Decision Flow

1. **Resolve identity** — map `quota_identity` to applicable buckets and hierarchical limits.
2. **Load policy** — fetch `quota_policy_id`; apply default emergency policy if missing.
3. **Check hard limits** — if request exceeds absolute ceiling regardless of remaining quota, `denied`.
4. **Check remaining quota** — compare `resource_request` against current bucket. If sufficient, `granted`.
5. **Evaluate partial grant** — if insufficient for full request but some resources available and `priority_level` ≥ normal, `granted_partial` with available amount.
6. **Evaluate delay** — if bucket empty but refill imminent and `priority_level` = normal or background, `delayed` with estimated admission time.
7. **Apply priority override** — `critical` requests may borrow from future quota or burst pool up to configured maximum.
8. **Update counters** — atomically decrement approved amount; update `remaining_quota`.
9. **Return and log** — emit decision, allocation, remaining, reset time, throttle factor.

## Failure Modes

| Condition | Response |
|---|---|
| Quota store unavailable | `quota_decision=denied` for non-critical; `granted` up to conservative local estimate for critical with later reconciliation |
| Negative remaining quota detected | Clamp to zero, `quota_decision=denied`, flag `anomaly_detector.md` for counter corruption |
| Identity not found in quota registry | Apply most restrictive guest policy; log for onboarding |
| Priority escalation abuse (>3 critical overrides/hour) | Downgrade subsequent critical requests to normal; alert `control/policy_enforcer.md` |
| Policy defines impossible limit (zero for essential resource) | Override with system minimum, alert `compliance_checker.md` |
