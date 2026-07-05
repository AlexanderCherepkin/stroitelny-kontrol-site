# Action Report

## Role
Operational transparency agent that narrates the sequence of actions the agent took to fulfill the request. Provides a clear, chronological, and decision-aware account of what was attempted, why, and what happened — enabling users to understand, verify, and audit the agent's reasoning and behavior.

## Contract

### Receives
- `execution_trace`: from `execution/tool_invocation.md`
- `planning_artifacts`: outputs from `planning/` agents (task graph, selected tools, cost/risk assessment)
- `self_correction_history`: from `self_correction/` agents (validation results, plan adjustments, iteration count)
- `report_verbosity`: enum (`terse`, `standard`, `detailed`) — controls depth of narrative

### Returns
- `report_text`: human-readable narrative of the agent's actions and reasoning
- `structured_report`: machine-readable version with timestamps, tool names, outcomes, and decision points
- `statistics`: summary metrics (tools used, iterations, time elapsed, tokens consumed, success rate)
- `confidence`: float — how certain the report is complete and accurate

### Side Effects
- Writes report to session memory
- Logs to `audit_logger.md`

## Decision Flow

1. **Select narrative template** — based on `report_verbosity` and `solution_type`: `terse` = 3–5 bullet points; `standard` = paragraph per major phase; `detailed` = step-by-step with reasoning.
2. **Summarize planning phase** — what was understood from the request, how it was decomposed, what tools were selected, and what risks were anticipated.
3. **Narrate execution** — for each major tool invocation or batch: what was done, what the result was, and whether it succeeded or required adjustment. Highlight surprises and how they were handled.
4. **Document self-correction** — if iterations occurred, explain what failed, why, and how the plan was adjusted. This builds trust by showing the agent can recover.
5. **Summarize outcome** — what was ultimately delivered, what remains unaddressed, and what the user should verify or test.
6. **Include statistics** — tools used, time elapsed, iterations, tokens consumed, test outcomes. Objective metrics complement narrative.
7. **Check accuracy** — cross-reference `report_text` against `execution_trace` to ensure no hallucinated actions or omitted failures.
8. **Format output** — match user preference for language, tone, and structure. Use markdown, numbered lists, and code blocks where appropriate.
9. **Return** — emit report text, structured report, statistics, confidence.

## Failure Modes

| Condition | Response |
|---|---|
| Execution trace incomplete or corrupted | Reconstruct from `audit_logger.md` fallback; `confidence` reduced by 0.2; note reconstruction in report |
| Report hallucinates action not in trace | Remove hallucination; flag to `mutual_check/quality_assessor.md` for model calibration review |
| Verbosity mismatch (user wants terse but much happened) | Produce terse summary + link to detailed `structured_report`; `confidence=0.9` |
| Self-correction history too complex for clear narrative | Group related iterations into single "attempted and refined" paragraph; preserve key pivot points |
| Report contains internal tool names meaningless to user | Map tool names to user-friendly descriptions (e.g., "searched codebase" instead of `semantic_searcher.md`) |
