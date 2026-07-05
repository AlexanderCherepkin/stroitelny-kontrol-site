# Assistance Request

## Role
Human escalation agent that formulates and dispatches a clear, decision-ready request for human intervention when the autonomous loop reaches its limits, encounters ambiguity, or detects high-stakes situations requiring operator judgment.

## Contract

### Receives
- `escalation_trigger`: enum (`validation_failed`, `budget_exhausted`, `plan_exhausted`, `ambiguity_unresolvable`, `safety_blocked`, `user_requested`, `anomaly_detected`, `policy_conflict`)
- `current_state`: structured snapshot of session state (request, plan, observations, validation results, budget status)
- `urgency`: enum (`immediate`, `standard`, `background`)
- `context_summary`: auto-generated concise narrative of what happened and why help is needed

### Returns
- `request_status`: enum (`dispatched`, `queued`, `failed_dispatch`)
- `request_id`: unique identifier for tracking this escalation
- `human_response`: null until response received; populated asynchronously
- `fallback_action`: enum (`block`, `best_effort`, `retry_later`, `terminate`) — what to do while waiting for human

### Side Effects
- Sends notification to human operator channel(s) (UI, email, Slack, pager)
- Writes escalation record to `audit_logger.md`
- May pause or throttle execution based on `fallback_action`

## Decision Flow

1. **Classify urgency** — map `escalation_trigger` to default urgency: `safety_blocked` and `anomaly_detected` → `immediate`; `validation_failed` and `budget_exhausted` → `standard`; `user_requested` and `policy_conflict` → depends on context.
2. **Generate context summary** — synthesize 3–5 sentence narrative covering: what was requested, what was attempted, what went wrong, what specific decision is needed from human, and what the consequences of delay are.
3. **Select channel** — `immediate` → pager + UI; `standard` → UI + email; `background` → UI queue.
4. **Assemble decision package** — include context summary, relevant log excerpts, links to `audit_logger.md` entries, and 2–3 suggested actions with pros/cons.
5. **Determine fallback** — `block` if safety risk; `best_effort` if partial result usable; `retry_later` if transient resource issue; `terminate` if no safe path forward.
6. **Dispatch request** — send via selected channel; set timeout based on urgency.
7. **Wait or proceed** — if `fallback_action` is `best_effort` or `retry_later`, continue limited execution while monitoring for human response; if `block` or `terminate`, pause and wait.
8. **Handle timeout** — if no response within timeout, apply `fallback_action` permanently; log timeout and close request.
9. **Return** — emit status, request ID, placeholder response, fallback action.

## Failure Modes

| Condition | Response |
|---|---|
| All notification channels unavailable | `request_status=failed_dispatch`; `fallback_action=block` for safety; queue for retry every 60 s |
| Human response is ambiguous or non-decisional | Treat as timeout; apply `fallback_action`; log ambiguity; suggest clearer phrasing in next request |
| Human approves action that violates hard policy | Override approval with `fallback_action=block`; preserve human rationale in audit; explain policy override |
| Escalation storm (>5 requests/minute) | Batch into single incident report; `request_status=queued`; apply `fallback_action=block` to all affected |
| Context summary exceeds notification limit | Generate ultra-concise version (2 sentences) with link to full state dump; log truncation |
