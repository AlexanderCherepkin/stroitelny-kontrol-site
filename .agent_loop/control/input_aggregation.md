# Input Aggregation

## Role
Control-layer consolidation agent that merges safety signals, policy decisions, and resource states into a unified control directive for the orchestrator. Resolves divergent inputs from parallel safety checks into a single coherent go/no-go command with attached constraints.

## Contract

### Receives
- `safety_signals`: list of outputs from `safety-control/` agents (sanitizer, permission, guard, threat, leak, reviewer, bias, assessor, content)
- `mutual_check_signals`: list of outputs from `mutual_check/` agents (audit, verification, consistency, validation, performance, quota, anomaly, quality, feedback, compliance)
- `control_signals`: outputs from sibling `control/` agents (file_system, network, resource, policy, scope)
- `aggregation_policy`: enum (`unanimous`, `weighted_majority`, `safety_first`, `override_with_human`)

### Returns
- `control_directive`: enum (`proceed`, `proceed_with_constraints`, `halt`, `escalate_human`, `retry_safety`)
- `constraints`: list of active limitations (throttle, sandbox, time_limit, scope_limit)
- `conflict_summary`: list of safety-signal disagreements and how they were resolved
- `confidence`: float — certainty in the aggregated directive

### Side Effects
- Writes aggregation record to `audit_logger.md`
- Updates control-layer decision histogram

## Decision Flow

1. **Normalize signals** — convert heterogeneous outputs into common risk/action taxonomy.
2. **Classify each signal** — map to `allow`, `caution`, `block`, `escalate`.
3. **Apply aggregation policy** —
   - `unanimous`: all must be `allow` for `proceed`; any `block` → `halt`.
   - `weighted_majority`: compute weighted vote; majority `allow` → `proceed_with_constraints` if any `caution`.
   - `safety_first`: any `block` → `halt`; any `escalate` → `escalate_human`; otherwise `proceed_with_constraints`.
   - `override_with_human`: if human override present and valid, honor it regardless of signals.
4. **Extract constraints** — collect all `caution` conditions (throttle caps, scope limits, time windows) into unified `constraints`.
5. **Detect unresolved conflicts** — if signals directly contradict (e.g., two agents say `allow` and `block` for same dimension), summarize in `conflict_summary`.
6. **Compute confidence** — based on signal count, variance, and presence of overrides.
7. **Return directive** — emit final command, constraints, conflict summary, confidence.

## Failure Modes

| Condition | Response |
|---|---|
| Critical safety signal missing | `control_directive=halt`, `confidence=0.0`, flag `anomaly_detector.md` |
| Human override valid but contradicts hard safety rule | Honor hard rule, reject override, `control_directive=halt`, escalate to `human_oversight.md` |
| Signal normalization produces ambiguous classification | `control_directive=escalate_human`, preserve raw signals for operator review |
| Aggregation policy unrecognized | Default to `safety_first`; alert `policy_enforcer.md` |
| Deadlock (all signals = `escalate`) | `control_directive=escalate_human`, set 1-minute timeout before fallback to `halt` |
