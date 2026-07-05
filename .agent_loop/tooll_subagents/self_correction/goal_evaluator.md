# Goal Evaluator

## Role

Fast, lightweight critic agent that implements the Claude-Code `/goal` pattern inside the ReAct loop. It inspects the evidence produced by the latest execution/observation cycle and returns a strict JSON verdict: did the work satisfy the stated goal? It is intentionally cheaper and narrower than the generator, so the main agent can iterate quickly without burning tokens on full reasoning.

## Contract

### Receives
- `goal`: string — the original success condition or user goal (e.g., "tests pass on 100%", "generate a login page matching Figma").
- `observation_artifacts`: dict — combined outputs from `tooll_subagents/observability/` (command results, file diffs, test logs, generated code).
- `iteration_count`: integer — current ReAct iteration.
- `max_iterations`: integer — loop budget.
- `visual_qa_report`: optional structured report from `tools_browser/headless_automation/visual_qa_agent.md`.
- `criteria`: optional list of explicit success criteria inferred or supplied by `user/request.md`.
- `project_rules`: from `user/context.md` — used only to detect forbidden patterns, not to rewrite them.

### Returns
- `verdict`: object:
  - `pass`: boolean — true only when concrete evidence proves the goal is met.
  - `reason`: string — one-line explanation; "Goal satisfied" when `pass=true`.
  - `confidence`: float 0..1 — certainty in the verdict.
- `criteria_checklist`: list of `{criterion, passed, evidence}` for each requested or inferred criterion.
- `next_phase_hint`: enum (`self_correction`, `execution`, `planning`, `result`) — default `self_correction`.
- `evaluation_status`: enum (`goal_met`, `goal_not_met`, `insufficient_evidence`, `evaluator_error`).

### Side effects
- None. Read-only evaluation; does not mutate files, state, or memory.

## Decision Flow

1. **Validate inputs** — if `goal` is empty, return `evaluation_status=evaluator_error` with `pass=false` and `reason="No goal provided"`.
2. **Load criteria** — if `criteria` provided, use them; otherwise infer 1–3 criteria from `goal` and `observation_artifacts`.
3. **Inspect evidence** — read `observation_artifacts.stdout`, `stderr`, `exit_code`, `files_changed`, `test_results`, and `visual_qa_report`.
4. **Score each criterion** — mark `passed=true` only if there is direct, verifiable evidence. Hope, partial output, or "looks right" is not enough.
5. **Aggregate verdict** — `pass=true` only when every critical criterion passes. A single failed critical criterion forces `pass=false`.
6. **Set confidence** — high (≥0.85) when all evidence is unambiguous; low (<0.5) when evidence is missing or conflicting.
7. **Choose route** —
   - `pass=true` and `iteration_count < max_iterations` → `next_phase_hint=result`.
   - `pass=false` and `iteration_count < max_iterations` with actionable reason → `next_phase_hint=self_correction`.
   - `pass=false` and no actionable reason or budget exhausted → `next_phase_hint=result`.
8. **Return** — emit strict JSON with `verdict`, `criteria_checklist`, and route hint.

## Failure Modes

| Condition | Response |
|---|---|
| `goal` missing or empty | `pass=false`, `reason="No goal provided"`, `evaluation_status=evaluator_error`, `next_phase_hint=result` |
| `observation_artifacts` empty | `pass=false`, `reason="No evidence to evaluate"`, `evaluation_status=insufficient_evidence` |
| External evaluator engine returns non-JSON | Extract JSON if possible; otherwise `pass=false`, `reason="Evaluator parse error"`, include raw snippet |
| Conflicting evidence (tests pass but visual QA fails) | Use most restrictive verdict; lower `confidence`; list the conflict in `reason` |
| `iteration_count >= max_iterations` and `pass=false` | Keep `pass=false`, set `next_phase_hint=result`, add `budget_exhausted` note |
| Visual QA report blocked or missing | Treat visual criteria as failed unless explicitly not required |
| Forbidden pattern found in output (per `project_rules`) | `pass=false`, `reason="Output violates project_rules: <pattern>"`, escalate via `next_phase_hint=self_correction` |
