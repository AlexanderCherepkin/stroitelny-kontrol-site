# Task Decomposition

## Role
Planning agent that breaks a high-level user request into atomic, ordered, and verifiable sub-tasks. Transforms ambiguous or complex goals into a structured execution graph that can be assigned to specialized tool agents.

## Contract

### Receives
- `parsed_request`: structured task descriptor from `request.md`
- `assembled_context`: context object from `context.md`
- `limitation_report`: limitations from `limitations.md`
- `decomposition_depth`: enum (`flat`, `standard`, `deep`) — controls granularity

### Returns
- `task_graph`: directed acyclic graph of sub-tasks with dependencies, estimated effort, and tool assignments
- `critical_path`: ordered list of sub-tasks that form the longest dependency chain
- `parallel_groups`: list of sub-task sets that can execute concurrently
- `verification_points`: list of milestones where progress can be validated
- `fallback_plan`: simplified alternative if primary plan hits blocking limitation

### Side Effects
- Writes plan to session memory for tracking and recovery
- Logs decomposition to `audit_logger.md`

## Decision Flow

1. **Analyze request type** — load decomposition template for `request_type` (code_change uses file→edit→test; question uses search→synthesize; debug uses reproduce→isolate→fix→verify).
2. **Identify primitives** — map request to atomic operations: read, write, search, execute, test, analyze, transform.
3. **Order dependencies** — determine which operations must precede others (cannot test before write, cannot write before read if append-only).
4. **Estimate effort** — assign relative cost (tokens, time, API calls) to each sub-task based on context size and operation complexity.
5. **Assign tools** — match each sub-task to the most appropriate `tools_*` category (read_file, search_code, replace_in_file, run_command, run_tests, etc.).
6. **Detect ambiguities** — if sub-task description is vague or lacks verification criteria, flag for `internal_monologue.md` clarification.
7. **Build fallback** — if `limitation_report` contains blocking items, construct reduced-scope plan that achieves partial value.
8. **Validate graph** — ensure no cycles, all leaf nodes have verification criteria, and graph depth respects `decomposition_depth`.
9. **Return** — emit task graph, critical path, parallel groups, verification points, fallback plan.

## Failure Modes

| Condition | Response |
|---|---|
| Request cannot be decomposed into known primitives | Return `task_graph=null`, `fallback_plan=["ASSISTANCE_REQUEST"]`, escalate to `internal_monologue.md` |
| Dependency graph contains cycle | Break cycle at lowest-priority edge; log broken dependency to `audit_logger.md` |
| All possible plans blocked by limitations | Return `fallback_plan` with maximum achievable scope; `recommendation=request_extension` |
| Decomposition exceeds token budget | Prune lowest-priority branches; mark as `truncated=true`; include pruning rationale |
| Tool assignment ambiguous (multiple candidates) | Assign all candidates with `disambiguation_needed` flag; route to `tool_plan_selection.md` |
