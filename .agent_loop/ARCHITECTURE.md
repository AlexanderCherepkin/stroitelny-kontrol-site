# Agent Loop Architecture

## Overview
Multi-agent AI system with hierarchical safety-first architecture. Central LLM agent orchestrates specialized sub-agents working through API, with strong emphasis on safety and verification at every step.

## Directory Tree

```
.agent_loop/
├── main_loop.md                          # Entry point — ReAct head agent
│
├── orchestrator/                         # API routing layer (6 agents)
│   ├── router.md                         #   Route calls between layers
│   ├── dispatcher.md                     #   Dispatch tasks to tool sub-agents
│   ├── pipeline_coordinator.md           #   Coordinate full pipeline execution
│   ├── state_manager.md                  #   Manage agent state across iterations
│   ├── api_gateway.md                    #   API gateway for external calls
│   └── message_bus.md                    #   Internal message bus
│
├── safety-control/                       # Safety input layer (9 agents)
│   ├── input_sanitizer.md                #   Sanitize user input
│   ├── permission_checker.md             #   Check action permissions
│   ├── command_guard.md                  #   Guard dangerous commands
│   ├── threat_detector.md                #   Detect security threats
│   ├── data_leak_preventer.md            #   Prevent data leaks
│   ├── output_reviewer.md                #   Review agent outputs
│   ├── bias_detector.md                  #   Detect bias in outputs
│   ├── safety_assessor.md                #   Assess action safety
│   ├── content_checker.md                #   Check content compliance
│   └── mutual_check/                     #   Cross-validation layer (10 agents)
│       ├── audit_logger.md               #     Log all actions
│       ├── action_verifier.md            #     Verify action correctness
│       ├── consistency_checker.md        #     Check data consistency
│       ├── result_validator.md           #     Validate results
│       ├── performance_monitor.md        #     Monitor performance
│       ├── quota_manager.md              #     Manage resource quotas
│       ├── anomaly_detector.md           #     Detect anomalies
│       ├── quality_assessor.md           #     Assess output quality
│       ├── feedback_aggregator.md        #     Aggregate feedback
│       └── compliance_checker.md         #     Check regulatory compliance
│
├── control/                              # Runtime control layer (7 agents)
│   ├── file_system_guard.md              #   Guard file system access
│   ├── network_guard.md                  #   Guard network access
│   ├── resource_monitor.md               #   Monitor resource usage
│   ├── human_oversight.md                #   Strategic human oversight
│   ├── policy_enforcer.md                #   Enforce runtime policies
│   ├── scope_manager.md                  #   Manage operation boundaries
│   └── input_aggregation.md              #   Aggregate control inputs
│
├── tooll_subagents/                      # ReAct cycle decomposition
│   ├── user/                             #   Input layer (4 agents)
│   │   ├── request.md                    #     User request
│   │   ├── context.md                    #     Execution context
│   │   ├── limitations.md                #     Known limitations
│   │   └── design_intake.md              #     Detect design-project inputs and emit a design_descriptor
│   ├── planning/                         #   Planning layer (13 agents)
│   │   ├── task_decomposition.md         #     Break down tasks
│   │   ├── cost_risk_assessment.md       #     Assess costs and risks
│   │   ├── tool_plan_selection.md        #     Select tools and plan
│   │   ├── internal_monologue.md         #     Internal reasoning
│   │   ├── figma_design_analyst.md       #     Run Figma pipeline and produce a design_blueprint
│   │   ├── design_to_code_planner.md     #     Decide technical_assignment vs full_code handoff
│   │   ├── backend_spec_bridge.md        #     Map backend specs to UI and generate backend layer
│   │   ├── responsive_composer.md        #     Generate breakpoint variants and constraint classes for Tailwind AST
│   │   ├── component_registry.md         #     Build Figma Component Registry and generate src/components/ui/*.tsx
│   │   ├── component_mapper.md           #     Map Figma Component Sets to React components and write mapper files
│   │   ├── ponytail_injector.md          #     Inject Ponytail protocol into code-generation system prompts
│   │   ├── ponytail_audit.md             #     Repository-wide over-engineering audit (read-only)
│   │   └── headroom_injector.md          #     Decide where Headroom context compression should be applied
│   ├── execution/                        #   Execution layer (4 agents)
│   │   ├── tool_invocation.md            #     Invoke selected tool
│   │   ├── safety_guardrails.md          #     Apply safety guardrails
│   │   ├── human_approval.md             #     Tactical human approval gate
│   │   └── action_logging.md             #     Log execution actions
│   ├── observability/                    #   Observation layer (12 agents)
│   │   ├── environment_result.md         #     Capture environment state
│   │   ├── runtime_output.md             #     Capture runtime output
│   │   ├── file_context.md               #     Capture file changes
│   │   ├── memory_enrichment.md          #     Enrich with memory context
│   │   ├── headroom_compressor.md        #     Compress large artifacts via Headroom CCR
│   │   ├── headroom_retriever.md         #     Restore original content by Headroom hash
│   │   ├── memanto_remember.md           #     Persist durable facts to Memanto semantic memory
│   │   ├── memanto_recall.md             #     Retrieve relevant prior context from Memanto
│   │   ├── memanto_answer.md             #     Synthesize grounded answers from Memanto memory
│   │   ├── mem0_remember.md              #     Persist durable conversation turns/facts to Mem0
│   │   ├── mem0_recall.md                #     Retrieve relevant prior context from Mem0
│   │   └── mem0_list.md                  #     List all memories stored in Mem0
│   ├── self_correction/                  #   Self-correction layer (5 agents)
│   │   ├── result_validation.md          #     Validate results
│   │   ├── plan_adjustment.md            #     Adjust plan if needed
│   │   ├── recursion_or_termination.md   #     Decide: loop or finish
│   │   └── assistance_request.md         #     Request human help
│   │   ├── ponytail_review.md            #     Over-engineering review for generated/refactored code
│   └── result/                           #   Output layer (4 agents)
│       ├── solution.md                   #     Final solution
│       ├── modified_files.md             #     List modified files
│       ├── action_report.md              #     Report actions taken
│       └── summary_recommendations.md    #     Summary and recommendations
│
└── tools_*/                              # Tool sub-agents (~110 agents)
    ├── tools_read/read_file/             #   File reading — linear pipeline (10 agents + read_optimizer)
    ├── tools_search/search_code/         #   Code search — diamond pipeline (10 agents + search_optimizer)
    ├── tools_replace/replace_in_file/    #   File editing — safety-gated pipeline (10 agents + edit_optimizer)
    ├── tools_runcom/run_command/         #   Command execution — sandboxed pipeline (11 agents + command_optimizer)
    ├── tools_runtest/run_tests/          #   Test running — framework-dispatch pipeline (10 agents + test_optimizer)
    ├── tools_terminal/terminal_io/       #   Terminal I/O — session-stateful pipeline (10 agents + terminal_optimizer)
    ├── tools_manangr/project_manager/    #   Project management — analysis-planning pipeline (10 agents + project_optimizer)
    ├── tools_database/database_query/    #   Database queries — query-lifecycle pipeline (10 agents + db_optimizer)
    ├── tools_web/web_request/            #   Web requests — request-lifecycle pipeline (10 agents + web_optimizer)
    ├── tools_memory/memory_store/        #   Memory storage — store-lifecycle pipeline (10 agents + memory_optimizer)
    ├── tools_browser/headless_automation/  #   Headless browser — automation pipeline (10 agents + browser_optimizer)
    │   ├── session_manager.md            #     Launch/dispose Playwright contexts
    │   ├── navigation_engine.md          #     Load URLs and wait for dynamic content
    │   ├── screenshot_agent.md           #     Capture viewport/full-page/element screenshots
    │   ├── dom_extractor.md              #     Extract dynamic DOM content after JS execution
    │   ├── selector_resolver.md          #     Resolve CSS/XPath selectors with retries
    │   ├── interaction_agent.md          #     Safe clicks, typing, scroll, form submission
    │   ├── network_interceptor.md        #     Capture and filter network traffic
    │   ├── cookie_storage_agent.md       #     Manage cookies/local/session storage
    │   ├── captcha_challenge_agent.md    #     Detect CAPTCHA/login walls and escalate
    │   ├── error_handler.md              #     Classify browser failures and trigger cleanup
    │   └── browser_optimizer.md          #     Batch operations and reuse contexts
    └── tools_lighthouse/audit/           #   Lighthouse hard-gate pipeline (10 agents + lighthouse_optimizer)
        ├── session_manager.md            #     Launch/dispose Playwright contexts for audits
        ├── navigation_engine.md          #     Stabilize page before audit
        ├── audit_runner.md               #     Run Lighthouse via Playwright
        ├── report_parser.md              #     Filter 500 KB report down to failed audits
        ├── metric_guard_performance.md   #     Enforce Performance = 100%
        ├── metric_guard_a11y.md          #     Enforce Accessibility = 100%
        ├── metric_guard_best_practices.md #     Enforce Best Practices = 100%
        ├── metric_guard_seo.md           #     Enforce SEO = 100%
        ├── correction_prompt_builder.md  #     Build compact correction prompt
        ├── loop_terminator.md            #     Convergence guard (8 iterations max)
        └── lighthouse_optimizer.md       #     Pipeline strategist and log rotation
```

## Flow

```
User Request
  → main_loop.md
    → orchestrator/router.md
      → safety-control/ (input sanitization, permission check, threat detection)
        → safety-control/mutual_check/ (cross-validation)
          → control/ (scope, policy, resource enforcement)
            → orchestrator/dispatcher.md
              → tooll_subagents/user/ (user context + project_rules.md + design_intake)
              → tooll_subagents/planning/ (task decomposition + figma_design_analyst + design_to_code_planner + memanto_recall)
              → tooll_subagents/execution/ (tool invocation)
                → tools_*/ (specialized tool agents)
                → tools_browser/headless_automation (Playwright dynamic pages)
                → tools_lighthouse/audit (Lighthouse hard-gate audit + report parsing + correction prompts)
                → mcp_servers/gateway.py (lazy MCP dispatch)
                → mcp_servers/figma_server.py (Figma-to-code pipeline)
                → mcp_servers/headroom_server.py (optional Headroom context-compression CCR tools)
                → mcp_servers/memanto_server.py (optional Memanto semantic-memory tools)
                → mcp_servers/mem0_server.py (optional Mem0 long-term memory tools)
              → tooll_subagents/observability/ (result capture + memanto_remember + mem0_remember)
              → tooll_subagents/self_correction/ (validate → adjust → loop or finish)
                → PhaseTransitionManager (runtime conditional phase routing)
              → tooll_subagents/result/ (final output + memanto_answer + mem0_recall)
  → User Response
```

## Agent Counts

| Layer | Count |
|---|---|
| main_loop | 1 |
| orchestrator | 6 |
| safety-control | 9 |
| safety-control/mutual_check | 10 |
| control | 7 |
| tooll_subagents | 42 |
| tools_* | 121 |
| **Total** | **196** |

## Naming Convention
- snake_case filenames
- Each agent follows the **Algorithmic template**: `# Agent Name`, `## Role`, `## Contract` (Receives/Returns/Side effects), `## Decision Flow` (numbered steps), `## Failure Modes` (Condition→Response table)
- Directory spelling: `tooll_subagents` (double "l"), `tools_manangr` (typo preserved)

## Key Decisions
1. Three-circuit safety: safety-control → mutual_check → control
2. ReAct cycle decomposed into atomic sub-steps per folder
3. Tools as microservices: 11 categories × 10+ agents with optimizer per category
4. Self-correction loop closes the cycle (validate → adjust → loop/terminate)
5. Human-in-the-loop split: strategic oversight (control) vs tactical approval (execution)
6. Double "l" in `tooll_subagents` and "manangr" typo preserved as-is in codebase
7. Lazy MCP gateway: `mcp_servers/gateway.py` exposes category metadata to the planner and materializes servers only when a tool is invoked, reducing planner token budget
8. `project_rules.md` in repo root is lightweight context loaded at session start and used as fallback policy source by `control/policy_enforcer.md`; updates require `human_approval.md`
9. Headless browser category: `tools_browser/headless_automation` adds Playwright-based dynamic page automation as the 11th tool category; runtime-only `mcp_servers/browser_server.py` keeps it optional and lazy
10. Lighthouse category: `tools_lighthouse/audit` adds a 12th tool category that runs Lighthouse via Playwright, parses reports, enforces 100% hard gate across Performance, Accessibility, Best Practices, and SEO, and feeds compact correction prompts back into the self-correction loop with a default convergence guard of 8 iterations
11. Conditional Edges: `runtime/engine/pipeline_runner.py` uses a `PhaseTransitionManager` to route between ReAct phases based on agent outputs instead of a hardcoded sequence
12. Ponytail protocol: `runtime/engine/ponytail_optimizer.py` injects the 7-step Ladder of Laziness into code-generation system prompts via `ponytail_injector.md`, while `ponytail_review.md` and `ponytail_audit.md` provide over-engineering review and audit capabilities
13. Headroom protocol: optional local LLM CCR layer exposed as MCP category `headroom` (`headroom_compress`, `headroom_retrieve`, `headroom_stats`) and as `runtime/engine/headroom_client.py`; integrated into ReAct planning, execution, observability, and `main_loop.md` context compaction; degrades to plaintext passthrough when `headroom-ai` is not installed
14. Memanto protocol: optional active semantic-memory agent exposed as MCP category `memanto` (`memanto_create_agent`, `memanto_remember`, `memanto_recall`, `memanto_answer`) and as `runtime/engine/memanto_client.py`; integrated into ReAct planning recall, observability remember, and end-of-session answer; degrades to in-memory fallback when the Memanto server is unreachable. Optional dependency: `runtime/requirements-memanto.txt`
15. Mem0 protocol: optional long-term memory layer exposed as MCP category `mem0` (`mem0_add`, `mem0_search`, `mem0_get_all`, `mem0_delete`) and as `runtime/engine/mem0_client.py`; integrated into ReAct planning recall, observability remember, and session cleanup; degrades to in-memory fallback when `mem0ai` is not installed or the API is unreachable. Optional dependency: `runtime/requirements-mem0.txt`

## Implementation Status

All 196 agents are fully implemented following the Algorithmic template:
- `main_loop.md` (1) — ReAct head agent orchestrating the full cycle with conditional phase transitions, Lighthouse hard-gate integration, and Headroom context-compaction integration
- `orchestrator/` (6) — router, dispatcher, pipeline_coordinator, state_manager, api_gateway, message_bus
- `safety-control/` (9) — input_sanitizer, permission_checker, command_guard, threat_detector, data_leak_preventer, output_reviewer, bias_detector, safety_assessor, content_checker
- `safety-control/mutual_check/` (10) — audit_logger, action_verifier, consistency_checker, result_validator, performance_monitor, quota_manager, anomaly_detector, quality_assessor, feedback_aggregator, compliance_checker
- `control/` (7) — file_system_guard, network_guard, resource_monitor, human_oversight, policy_enforcer, scope_manager, input_aggregation
- `tooll_subagents/` (42) — Full ReAct cycle across 6 phases: user (4 with `design_intake.md`), planning (13 with `figma_design_analyst.md`, `figma_precise_mode_auditor.md`, `design_to_code_planner.md`, `backend_spec_bridge.md`, `responsive_composer.md`, `component_registry.md`, `component_mapper.md`, `ponytail_injector.md`, `ponytail_audit.md`, and `headroom_injector.md`), execution (4), observability (12 with `headroom_compressor.md`, `headroom_retriever.md`, `memanto_remember.md`, `memanto_recall.md`, `memanto_answer.md`, `mem0_remember.md`, `mem0_recall.md`, and `mem0_list.md`), self_correction (5 with `ponytail_review.md`), result (4)
- `tools_*` (121) — 12 categories × 10+ agents each with cross-cutting optimizers, including `tools_browser/headless_automation` for Playwright-based dynamic web automation and `tools_lighthouse/audit` for Lighthouse 100% hard-gate audits
- `mcp_servers/figma_server.py` — lazy MCP wrapper around `figma-agent-core/` exposing the Figma-to-code pipeline, including design-token extraction (`figma_extract_tokens`), component registry (`figma_build_component_registry`), reusable component extraction (`figma_extract_components`), responsive breakpoint composition (`figma_responsive_compose`), and Playwright-based Visual QA with automatic Figma reference download and structural layout checks
- `mcp_servers/backend_server.py` — lazy MCP wrapper around the Backend Spec Bridge, exposing `backend_run_bridge` for fullstack UI+backend generation
- `mcp_servers/memanto_server.py` — lazy MCP wrapper around `runtime/engine/memanto_client.py` exposing `memanto_create_agent`, `memanto_remember`, `memanto_recall`, and `memanto_answer`; degrades to in-memory fallback when the Memanto server is unreachable
- `mcp_servers/mem0_server.py` — lazy MCP wrapper around `runtime/engine/mem0_client.py` exposing `mem0_add`, `mem0_search`, `mem0_get_all`, and `mem0_delete`; degrades to in-memory fallback when `mem0ai` is not installed or the API is unreachable

Zero remaining stubs. All agents include Role, Contract, Decision Flow, and Failure Modes.

## Runtime / MCP

- `runtime/engine/pipeline_runner.py` — loads `project_rules.md` at session start and injects it into planning; creates `mcp_servers/gateway.py` with lazy server factories.
- `runtime/engine/llm_engine.py` — `LLMConfig.mcp_enabled` flag controls whether MCP categories are presented to the planner.
- `mcp_servers/registry.py` — supports eager and lazy server registration; lazy registration keeps category metadata without holding live server instances.
- `mcp_servers/bootstrap.py` — `--eager` flag for `--test`/`--serve`; default lazy mode constructs servers only on first tool call.
- `mcp_servers/gateway.py` — exposes `categories()`, `category_metadata()`, `tools_for_category()`, and `execute()` without loading unused servers.
- `mcp_servers/browser_server.py` — optional Playwright-based browser automation server; lazy-loaded and falls back gracefully if Playwright is unavailable.
- `mcp_servers/figma_server.py` — optional Figma-to-code pipeline server wrapping `figma-agent-core/`; lazy-loaded and reports degraded if `figma-agent-core/` is missing or `FIGMA_TOKEN`/`FIGMA_URL` are unset.
- `mcp_servers/backend_server.py` — optional Backend Spec Bridge server wrapping `figma-agent-core/backend_bridge.py`; lazy-loaded and reports degraded if `figma-agent-core/` is missing or no backend spec is provided.
- `runtime/requirements-browser.txt` — optional Playwright dependency file; core `runtime/requirements.txt` stays lightweight.
- `runtime/requirements-memanto.txt` — optional Memanto SDK/server dependency file.
- `runtime/requirements-mem0.txt` — optional Mem0 Python SDK dependency file.
- `runtime/engine/memanto_client.py` — singleton HTTP client for Memanto REST API with in-memory fallback when the server is unavailable.
- `runtime/engine/mem0_client.py` — singleton wrapper around the `mem0ai` `Memory`/`MemoryClient` classes with in-memory fallback when the SDK/API is unavailable.
- `runtime/engine/pipeline_runner.py` — also hosts `PhaseTransitionManager` for conditional ReAct phase routing.
- `project_rules.md` — lightweight project-level context file in repo root (Scope, Conventions, Tooling Preferences, Safety Defaults, Human-in-the-Loop Triggers).

## Validation

### Cross-Reference Integrity

All 187 agents are wired into a single reference graph. Every agent is reachable from at least one other agent, and no agent references a missing file.

**Test results (2026-06-10):**
- Broken links: 0 (6 known false positives filtered — `README.md`, `API.md`, `CHANGELOG.md`, `MEMORY.md`, `project_rules.md` are documentation targets, not agents)
- Isolated agents: 0 (previously 18; fixed by adding links into category optimizers)
- Script: `scripts/validate_cross_references.js` — run with `node scripts/validate_cross_references.js` to re-check after any edit

**Top referenced agents:**
- `audit_logger.md` — referenced by 21 agents (central logging backbone)
- `resource_monitor.md` — referenced by 18 agents (resource governance)
- `anomaly_detector.md` — referenced by 15 agents (behavioral forensics)
- `state_manager.md` — referenced by 14 agents (session persistence)
- `human_oversight.md` — referenced by 12 agents (strategic approval)
