# Tool Plan Selection

## Role
Dispatch-planning agent that selects the optimal sequence of tool categories and specific tool agents for each sub-task in the task graph. Resolves ambiguities from `task_decomposition.md` and ensures tool compatibility across the pipeline.

## Contract

### Receives
- `task_graph`: from `task_decomposition.md`
- `cost_risk_assessment`: from `cost_risk_assessment.md`
- `available_tools`: current inventory of functional tool agents with status and capability metadata
- `project_rules`: from `user/context.md` — lightweight project-level rules
- `mcp_categories`: list of available MCP category names (lazy metadata, no full tool descriptions)
- `execution_policy`: enum (`speed_priority`, `accuracy_priority`, `cost_priority`, `safety_priority`)

### Returns
- `tool_plan`: ordered list of tool invocations with parameters, expected outputs, and fallback tools
- `pipeline_compatibility`: boolean — whether all selected tools can chain without format mismatch
- `contingency_plan`: list of tool substitutions if primary tool fails
- `estimated_end_to_end_latency`: milliseconds or relative time units

### Side Effects
- Updates tool selection telemetry for future optimization
- Logs plan to `audit_logger.md`

## Decision Flow

1. **Iterate sub-tasks** — for each node in `task_graph` critical path and parallel groups.
2. **Map to tool categories** — use capability matrix: read → `tools_read`, search → `tools_search`, write → `tools_replace`, execute → `tools_runcom`, test → `tools_runtest`, terminal → `tools_terminal`, browse/render/screenshot/dynamic_page → `tools_browser`, mcp → `mcp_servers/gateway.py`, design_project/Figma ingestion → `figma` MCP category (`figma_bootstrap`, `figma_analyze`, `figma_generate_spec`, `figma_extract_tokens`, `figma_responsive_compose`, `figma_build_component_registry`, `figma_extract_components`, `figma_map_interactions`, `figma_generate_component`, `figma_download_assets`, `figma_run_pipeline`) and `tooll_subagents/planning/responsive_composer.md` for breakpoint variant planning, `tooll_subagents/planning/component_registry.md` for Component Set/Variant planning, and `tooll_subagents/planning/asset_agent.md` for asset-download planning (batching, 429 backoff, skip-existing, optimization). backend specification mapping → `backend` MCP category (`backend_analyze_spec`, `backend_map_ui`, `backend_generate_routes`, `backend_generate_actions`, `backend_sync_schema`, `backend_run_bridge`), etc. If `project_rules.tooling_preferences` is present, boost rank of preferred tools and demote discouraged/disallowed ones; if a required tool is discouraged, escalate to `control/policy_enforcer.md`. Only include MCP categories listed in `mcp_categories` to avoid loading servers for unused capabilities; when a `design_blueprint` is present, `mcp_categories` must include `figma`; when a `backend_spec` is present, `mcp_categories` must include `backend`.
   - **Ponytail injection** — before any code-generation or refactoring step, insert `ponytail_injector.md` to prepend the Ponytail protocol to the target agent's system prompt when the effective mode is not `off` and the task is coding-related. If the user invokes `/ponytail-audit`, insert `ponytail_audit.md` as a standalone read-only planning step.
   - **Headroom injection** — if `headroom_enabled=true` (resolved from input, env `HEADROOM_ENABLED`, or default `true`) and the `headroom` MCP category is available, insert `headroom_injector.md` as a planning step after `tool_plan_selection` produces the initial plan. The injector scans the plan for heavy context producers (large tool outputs, logs, RAG chunks, multi-agent handoffs) and appends `headroom_compressor.md` / `headroom_retriever.md` observation steps where compression will materially reduce context usage without blocking critical detail. If Headroom is unavailable or disabled, skip this step with a single log line.
   - **Memanto injection** — if `memanto_enabled=true` (resolved from input, env `MEMANTO_ENABLED`, or default `true`) and the `memanto` MCP category is available, insert `memanto_recall.md` as the first planning step with `query` derived from the user's goal and `tags=["project_rules", "constraints", "preferences"]`. After task decomposition, insert `memanto_remember.md` to persist the approved plan, constraints, and user preferences as typed memories. If Memanto is unavailable or disabled, skip these steps with a single log line.
   - **Mem0 injection** — if `mem0_enabled=true` (resolved from input, env `MEM0_ENABLED`, or default `true`) and the `mem0` MCP category is available, insert `mem0_recall.md` as the first planning step with `query` derived from the user's goal. After task decomposition, insert `mem0_remember.md` to persist the approved plan, constraints, and user preferences. If Mem0 is unavailable or disabled, skip these steps with a single log line.
3. **Rank candidates** — within category, score tools by alignment with `execution_policy` (speed, accuracy, cost, safety weights).
4. **Check compatibility** — verify output format of tool N matches input expectations of tool N+1; flag mismatches.
5. **Resolve conflicts** — if two sub-tasks claim the same mutable resource (file, database row), serialize or partition access.
6. **Build contingency** — for each primary tool, select fallback from same or adjacent category with lower capability but higher reliability.
7. **Optimize pipeline** — reorder where possible to reduce context switching (group all reads, then all writes, then tests).
8. **Estimate latency** — sum tool latencies plus orchestration overhead; add parallel-group savings.
9. **Validate policy** — ensure no selected tool is currently prohibited by active policy or safety hold.
10. **Return** — emit tool plan, compatibility flag, contingency plan, latency estimate.

## Failure Modes

| Condition | Response |
|---|---|
| No tool available for required sub-task | Flag `pipeline_compatibility=false`; include `contingency_plan=["ASSISTANCE_REQUEST"]`; halt planning |
| Selected tool marked degraded by `performance_monitor.md` | Auto-select contingency as primary; log degradation impact |
| Policy prohibits selected tool for this request context | Replace with next-ranked permitted tool; if none, `recommendation=escalate` to `control/policy_enforcer.md` |
| Format mismatch between chained tools | Insert adapter sub-task or select alternative tool; if unresolvable, `pipeline_compatibility=false` |
| `project_rules` conflict with `execution_policy` | Escalate to `control/policy_enforcer.md` with `conflict_resolution_mode=most_restrictive` |
| Required tool discouraged by `project_rules` | Select fallback; if no viable fallback, `pipeline_compatibility=false` and escalate |
| Tool plan exceeds token budget for prompt assembly | Prune non-critical tool parameters; use compressed parameter schema |
| Coding task plan missing `ponytail_injector.md` | Insert it before code-generation steps; log to `audit_logger.md` |
| `/ponytail-audit` requested but `ponytail_audit.md` unavailable | Skip audit step; report unavailable tool; continue with main plan |

