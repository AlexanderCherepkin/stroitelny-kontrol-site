# Safety Guardrails

## Role
Tactical safety layer applied during execution to catch runtime-specific risks that static planning could not predict. Monitors live tool behavior, enforces execution boundaries, and can pause or abort operations if emergent threats appear.

## Contract

### Receives
- `active_execution`: current tool invocation descriptor and partial output stream
- `live_risk_threshold`: float 0.0–1.0 — dynamic threshold based on environment and policy
- `guardrail_rules`: runtime-specific rules (e.g., max file size written, max network bytes, forbidden path patterns)
- `observation_window`: seconds of recent behavior to evaluate

### Returns
- `guardrail_status`: enum (`clear`, `warning`, `paused`, `aborted`)
- `triggered_rules`: list of rules that fired with severity and evidence
- `mitigation_applied`: list of automatic actions taken (throttled, truncated, blocked)
- `recommendation`: enum (`proceed`, `resume_with_limits`, `abort_and_report`, `escalate_to_human`)
- `next_phase_hint`: enum (`observability`, `execution`, `result`) — suggested next ReAct phase after guardrail verdict

### Side Effects
- Can send pause/abort signals to running tool execution
- Writes guardrail events to `audit_logger.md`
- Updates live risk model weights

## Decision Flow

1. **Stream observation** — subscribe to tool output stream, resource counters, and side-effect telemetry during `observation_window`.
2. **Rule evaluation** — continuously evaluate `guardrail_rules` against observed behavior.
3. **Pattern detection** — check for emergent patterns: rapid file growth, unexpected network egress, recursive self-invocation, output containing sensitive tokens.
4. **Risk scoring** — compute composite risk score from triggered rules; if score exceeds `live_risk_threshold`, escalate status.
5. **Determine status** — `clear` if all rules pass; `warning` if minor threshold exceeded (log only); `paused` if major threshold exceeded (pause execution, request plan adjustment); `aborted` if critical threshold exceeded (terminate execution, preserve state).
6. **Apply mitigation** — auto-truncate oversized output, auto-block forbidden paths, auto-throttle excessive API calls.
7. **Recommend next step** — `proceed` if clear; `resume_with_limits` if paused and plan adjusted; `abort_and_report` if aborted; `escalate_to_human` if critical and ambiguous.
8. **Return** — emit status, triggered rules, mitigations, recommendation.

## Failure Modes

| Condition | Response |
|---|---|
| Guardrail stream lag exceeds safety window | `guardrail_status=paused`, `recommendation=escalate_to_human` until stream catches up |
| Rule definition circular or self-referencing | Disable offending rule; `guardrail_status=warning`; flag `control/policy_enforcer.md` |
| Tool ignores pause signal | `guardrail_status=aborted`, force-terminate tool process; preserve partial output |
| Live risk model produces oscillating scores | Apply hysteresis (must exceed threshold for 3 consecutive samples); log oscillation |
| Mitigation action itself violates policy | Revert mitigation; `guardrail_status=aborted`; `recommendation=escalate_to_human` |
