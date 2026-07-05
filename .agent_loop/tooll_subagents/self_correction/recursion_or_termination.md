# Recursion or Termination

## Role
Loop-control agent that decides whether the ReAct cycle should continue with a revised plan or terminate and deliver the current result. Balances convergence, resource budgets, and user expectations against diminishing returns from further iteration.

## Contract

### Receives
- `validation_result`: from `self_correction/result_validation.md`
- `plan_adjustment`: from `self_correction/plan_adjustment.md` (or null if no adjustment attempted)
- `iteration_count`: integer — how many ReAct cycles completed so far
- `lighthouse_iteration_count`: integer — how many Lighthouse refinement iterations completed so far
- `lighthouse_max_iterations`: integer (default 8)
- `budget_status`: remaining tokens, time, API calls, and cost from `cost_risk_assessment`
- `user_escalation_flag`: boolean — whether user explicitly requested human takeover

### Returns
- `decision`: enum (`recurse`, `terminate_success`, `terminate_partial`, `terminate_failure`, `escalate_human`)
- `termination_reason`: human-readable rationale for the decision
- `deliverable`: pointer to the result payload to return (may be best-effort partial result)
- `next_action`: if `recurse`, pointer to `adjusted_plan` to execute; if `escalate_human`, escalation request descriptor
- `next_phase_hint`: enum (`execution`, `planning`, `result`) — suggested next ReAct phase (default `result` for terminate/escalate decisions)

### Side Effects
- Updates session iteration counter
- Logs decision to `audit_logger.md`
- May trigger `control/human_oversight.md` if `escalate_human`

## Decision Flow

1. **Check user escalation** — if `user_escalation_flag=true`, `decision=escalate_human` immediately; preserve current state.
2. **Check budget exhaustion** — if any budget dimension exhausted (tokens=0, time exceeded, cost cap reached), `decision=terminate_partial` if any result exists; `terminate_failure` if nothing usable; include budget exhaustion in `termination_reason`.
3. **Evaluate validation** — if `validation_result.validation_status=complete`, `decision=terminate_success`.
4. **Evaluate partial success** — if `validation_status=partial` and `plan_adjustment` exists and `iteration_count < max_replanning_attempts` and budget allows, `decision=recurse`.
5. **Evaluate partial success with no adjustment** — if `validation_status=partial` but `plan_adjustment` is null or exhausted, `decision=terminate_partial` with `deliverable` as best-effort.
6. **Evaluate failure** — if `validation_status=failed` and `retry_recommended=true` and budget allows, `decision=recurse` with `plan_adjustment`.
7. **Evaluate failure with no hope** — if `validation_status=failed` and `retry_recommended=false` or budget exhausted, `decision=terminate_failure` with diagnostic `termination_reason`.
8. **Evaluate inconclusive** — if `validation_status=inconclusive` and iteration_count low, `decision=recurse` with information-gathering plan; if iterations high, `decision=escalate_human`.
9. **Lighthouse hard-gate check** — if `validation_result.lighthouse_status` is present:
    - `passed` → treat as contribution toward `terminate_success`.
    - `needs_refinement` and `lighthouse_iteration_count < lighthouse_max_iterations` → `decision=recurse`; route next action through `plan_adjustment.md` with Lighthouse `correction_prompt`.
    - `max_iterations_reached` → `decision=escalate_human`; include final Lighthouse failure log in `deliverable`; route to `assistance_request.md`.
10. **Diminishing returns check** — if `validation_status` unchanged across last 2 iterations (no improvement), `decision=terminate_partial` to prevent infinite loop; log stagnation.
11. **Repeated gap detection** — inspect `gap_analysis` from `validation_result`. If any gap reason or description substring has appeared in the previous two cycles' `gap_analysis` (deduplicated by normalized string), the same root cause has failed twice; override to `decision=escalate_human` with `next_action=different_approach` (e.g. route to `assistance_request.md` or `control/human_oversight.md`), unless `user_escalation_flag=true`, which already escalates at step 1.
12. **Return** — emit decision, reason, deliverable, next action.

## Failure Modes

| Condition | Response |
|---|---|
| Iteration count corrupted or negative | Reset to 0; `decision=recurse` if budget allows; else `terminate_failure` |
| Budget status contradictory (time exceeded but tokens remain) | Honor most restrictive dimension; `decision=terminate_partial` with explicit budget reason |
| Validation result and plan adjustment both null | `decision=escalate_human`; cannot determine state |
| Terminate decision but no deliverable exists | `decision=terminate_failure`; `deliverable` includes apology and diagnostic request |
| Recurse loop detected (>3 identical adjustments) | `decision=escalate_human`; log pattern to `feedback_aggregator.md` |
| Same gap reason appears in two consecutive cycles | `decision=escalate_human`; `next_action=different_approach`; route to `assistance_request.md` or `control/human_oversight.md` |
| Lighthouse `max_iterations_reached` | `decision=escalate_human`; `next_action=assistance_request.md`; include final failure log |
| Lighthouse `needs_refinement` with budget left | `decision=recurse`; `next_action=plan_adjustment.md` with `correction_prompt` |
| Lighthouse scores perfect but other validation fails | Honor the stricter verdict; do not auto-terminate on Lighthouse alone |
