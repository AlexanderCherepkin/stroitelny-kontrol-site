# Lighthouse Loop Terminator

## Role
Convergence guard for the Lighthouse refinement loop. Decides whether to continue refining the front-end code, accept the current result, or escalate to a human after the 5-iteration hard limit is reached.

## Contract

### Receives
- `category_scores`: current 0–1 scores per category
- `iteration_count`: integer — how many Lighthouse refinement iterations have run
- `max_iterations`: integer (default 8)
- `correction_prompt`: from `tools_lighthouse/audit/correction_prompt_builder.md`
- `previous_scores`: optional list of score dicts from prior iterations for stagnation detection

### Returns
- `decision`: enum (`recurse`, `terminate_success`, `terminate_partial`, `escalate_human`)
- `final_scores`: dict of latest category scores
- `escalation_reason`: optional human-readable reason when decision is `escalate_human`
- `next_action`: pointer to `adjusted_plan` if `recurse`, or to `assistance_request.md` if `escalate_human`

### Side effects
- Writes convergence decision to `safety-control/mutual_check/audit_logger.md`
- Writes final filtered failure log to `.logs/lighthouse/YYYY-MM-DD/HH-MM-SS-<run-id>/iteration-05-final.json`

## Decision Flow

1. **Check perfect scores** — if all four categories score 1.0, `decision=terminate_success` immediately.
2. **Check iteration budget** — if `iteration_count >= max_iterations`, `decision=escalate_human` with `escalation_reason="Lighthouse hard gate not reached after {max_iterations} iterations"`.
3. **Check stagnation** — if `previous_scores` shows no category improved over the last 2 iterations, `decision=escalate_human` with reason "Metrics stuck; different approach needed". Also escalate if the same `correction_prompt` is emitted unchanged for 2 consecutive iterations.
4. **Check diminishing returns** — if total score gap improved by < 0.05 over the last iteration and `iteration_count >= 3`, `decision=escalate_human` with reason "Diminishing returns".
5. **Continue refining** — otherwise `decision=recurse`; attach `correction_prompt` to `next_action`.
6. **Return** — emit decision, scores, escalation reason, next action.

## Failure Modes

| Condition | Response |
|---|---|
| `iteration_count` corrupted or negative | Reset to current known value; if budget exhausted, `escalate_human` |
| `max_iterations` missing | Default to 5; log assumption |
| Scores contradictory (passed=true but score < 1.0) | Honor score value; treat as not passed; log anomaly to `mutual_check/anomaly_detector.md` |
| Convergence storm (>1 escalation per minute) | Batch into single incident; `decision=escalate_human`; queue to `assistance_request.md` |
