# Lighthouse Correction Prompt Builder

## Role
Builds a compact, token-efficient correction prompt from the four metric-guard correction lists. The prompt is consumed by `tooll_subagents/planning/plan_adjustment.md` and `tooll_subagents/execution/tool_invocation.md` to drive the next refinement iteration.

## Contract

### Receives
- `performance_corrections`: from `tools_lighthouse/audit/metric_guard_performance.md`
- `a11y_corrections`: from `tools_lighthouse/audit/metric_guard_a11y.md`
- `best_practices_corrections`: from `tools_lighthouse/audit/metric_guard_best_practices.md`
- `seo_corrections`: from `tools_lighthouse/audit/metric_guard_seo.md`
- `category_scores`: dict of current 0–1 scores
- `iteration_count`: integer
- `max_iterations`: integer (default 5)

### Returns
- `correction_prompt`: markdown string with current scores, target (100%), and ordered required changes
- `target_files`: list of file paths mentioned in corrections
- `severity`: enum (`critical`, `major`, `minor`) based on score gap and iteration count

### Side effects
- Writes `correction_prompt` to `<workspace>/.tmp/lighthouse/<session_id>/iteration-<iteration_count>-correction`
- Logs to `safety-control/mutual_check/audit_logger.md`

## Decision Flow

1. **Drop empty categories** — omit any metric guard list that is `passed=true` or empty.
2. **Deduplicate** — merge corrections that target the same selector/file/issue; keep the highest priority.
3. **Sort** — order by `priority` (critical → major → minor), then by category (performance, a11y, best-practices, seo).
4. **Format header** — include current scores, target 100%, iteration counter (`iteration_count/max_iterations`).
5. **Format body** — for each correction emit:
   - `[МЕТРИКА] issue`
   - `Требование: required_change`
   - `Файл/селектор: file? selector?`
6. **Append safe-component reminder** — add: "Используй только компоненты из `src/components/safe/`: `SafeLink`, `ResponsivePicture`, `TouchSafeElement`. Стандартные `<a>`, `<img>`, `<div onclick>` запрещены."
7. **Determine severity** — `critical` if any score < 0.95 or iteration_count == max_iterations; `major` if any score < 1.0; `minor` if only trivial issues remain.
8. **Return** — emit `correction_prompt`, `target_files`, `severity`.

## Failure Modes

| Condition | Response |
|---|---|
| All corrections empty but scores not 100% | Emit generic "reach 100% on all Lighthouse categories" prompt with severity=critical |
| Iteration count at max | Add `[FINAL ITERATION]` warning and escalate severity to critical |
| Target file outside workspace | Replace with relative path and flag to `control/file_system_guard.md` |
| Prompt exceeds token budget | Truncate lowest-priority corrections; add ellipsis note |
