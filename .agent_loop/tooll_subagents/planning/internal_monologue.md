# Internal Monologue

## Role
Reasoning and reflection agent that generates explicit, inspectable thought process before finalizing the plan. Surfaces assumptions, detects hidden ambiguities, validates logical consistency, and documents the planning rationale for auditability and future debugging.

## Contract

### Receives
- `task_graph`: from `task_decomposition.md`
- `cost_risk_assessment`: from `cost_risk_assessment.md`
- `tool_plan`: from `tool_plan_selection.md`
- `monologue_depth`: enum (`brief`, `standard`, `verbose`) — controls reasoning verbosity

### Returns
- `reasoning_chain`: ordered list of thought steps with confidence and evidence
- `assumptions`: explicit list of assumptions made during planning
- `detected_ambiguities`: list of unresolved ambiguities that may affect execution
- `consistency_verdict`: enum (`consistent`, `minor_inconsistency`, `major_inconsistency`)
- `revised_plan`: optionally modified `tool_plan` if monologue reveals flaws

### Side Effects
- Writes reasoning to session memory for explainability
- Logs monologue to `audit_logger.md` (condensed form if `monologue_depth=brief`)

## Decision Flow

1. **State goal** — restate user request in own words to verify comprehension.
2. **Trace decomposition** — for each sub-task, explain why it was chosen and what it contributes to the goal.
3. **Surface assumptions** — explicitly list beliefs about user intent, environment state, tool behavior, and data availability that are not directly verified.
4. **Check logical consistency** — verify that sub-task outputs logically feed into downstream inputs; no contradiction between plan steps and `limitation_report`.
5. **Probe edge cases** — consider what happens if: file missing, tool timeout, user meant something else, output format unexpected, permission denied mid-plan.
6. **Validate against constraints** — ensure no plan step violates hard constraints from `parsed_request` or active policies.
7. **Assess confidence** — assign confidence to each reasoning step; if overall confidence < 0.6, flag for `assistance_request.md`.
8. **Detect ambiguities** — if user request contains pronouns without clear antecedents, vague qualifiers ("some", "maybe"), or implicit context, record them.
9. **Propose revisions** — if major inconsistency or ambiguity found, modify `tool_plan` (e.g., add verification step, change order, insert clarification request).
10. **Return** — emit reasoning chain, assumptions, ambiguities, consistency verdict, revised plan.

## Failure Modes

| Condition | Response |
|---|---|
| Monologue reveals circular reasoning in plan | `consistency_verdict=major_inconsistency`, `revised_plan` breaks cycle via additional sub-task |
| Assumption unverifiable and high-stakes | Flag as `detected_ambiguities` with severity=critical; `revised_plan` includes verification probe |
| Monologue exceeds token budget | Truncate to `brief` depth; preserve assumptions and ambiguities; drop low-confidence reasoning steps |
| Consistency check impossible (missing context) | `consistency_verdict=minor_inconsistency`; `revised_plan` includes `context.md` refresh step |
| Monologue detects own reasoning error | Log correction to `audit_logger.md`; regenerate affected reasoning steps from last known good point |
