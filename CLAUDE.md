# CLAUDE.md — Agentic Loop

This is a **multi-agent AI system** with hierarchical safety-first architecture.
196 agents across 6 layers. The 110 tool-category agents (`tools_*`) are fully implemented
following the Algorithmic template (Role + Contract + Decision Flow + Failure Modes).
All 196 agents across all 6 layers are fully implemented with the Algorithmic template.
No remaining stubs.

## First Action (always)

1. **Find the technical assignment** — search the project root and subdirectories for
   `TECHNICAL_ASSIGNMENT.md` (техническое задание). This is the requirements baseline.
   If it exists, read it first — it defines WHAT and WHY before you look at HOW.
2. **Interview the user** — immediately after reading the assignment, conduct a structured
   interview to clarify ambiguities, fill gaps, and confirm understanding:
   - What is the problem being solved? Who is the end user?
   - What are the hard constraints? (deadlines, budget, tech stack, compliance)
   - What does "done" look like? (acceptance criteria, success metrics)
   - What are the known risks or unknowns?
   - Are there existing systems to integrate with or migrate from?
   Ask control questions that can only be answered if the assignment was understood correctly.
   Do NOT proceed to architecture until the user confirms the interview is complete.

   **Gate 1 — Start-of-project confirmation**
   - After the interview, explicitly ask: **"Interview complete. Proceed with development?"**
   - Do not write code, edit files, or run generators until the user answers yes/proceed/continue.

3. **Read `.agent_loop/ARCHITECTURE.md`** — the definitive architecture reference.
   Contains the full directory tree, data flow diagram, agent counts, and naming conventions.

## Approval Gates (autonomous-bot configuration)

This project runs as an autonomous bot. Only the following two gates require human confirmation; all other operations are auto-approved and must not interrupt execution.

1. **Gate 1 — Interview confirmation**
   - Ask **"Interview complete. Proceed with development?"** only when a structured interview is explicitly required.
   - If the user has already directed development (e.g., issued a concrete task), the gate is satisfied; do not ask again.

2. **Gate 2 — Pre-preview / pre-deployment / local-hosting**
   - Before build, preview, publish, deploy, `git push`, hosting exposure, or any action that makes the project reachable on the internet or local hosting for visualization, stop and ask: **"Project is ready for preview/deployment. Proceed?"**

Auto-approved operations (non-exhaustive):
- File reads, glob, grep, directory listings.
- Searches for PRD/specification files and discovery tasks.
- Running tests, linters, validators, and local dev servers that do not expose the project externally.
- Internal reasoning, planning, and architecture review.
- File edits, code generation, command execution, agent creation, and documentation updates inside the workspace.
- Network egress to configured allow-list destinations.
- Browser automation on trusted domains.

Never auto-approve (still require confirmation):
- Deployment, push, production publish, or exposure to the internet/local hosting.
- Updates to `project_rules.md` or `CLAUDE.md` unless the change is directly ordered by the user.

## Quick Reference

| Layer | Count | Purpose | Status |
|---|---|---|---|
| main_loop | 1 | Entry point — ReAct head agent | FILLED |
| orchestrator | 6 | API routing layer | FILLED |
| safety-control | 9 | Input safety (sanitization, permissions, threats) | FILLED |
| safety-control/mutual_check | 10 | Cross-validation (audit, consistency, compliance) | FILLED |
| control | 7 | Runtime enforcement (scope, policy, resources) | FILLED |
| tooll_subagents | 42 | ReAct cycle: user→planning→execution→observability→self_correction→result, including Ponytail injector/review/audit, Headroom injector/compressor/retriever, Memanto remember/recall/answer, and Mem0 remember/recall/list | FILLED |
| tools_read | 10 | Read-file pipeline (path→encoding→read→chunk→parse→extract→integrity→cache→format) | FILLED |
| tools_replace | 10 | Replace-file pipeline (backup→pattern→edit→diff→rank→validate→write→verify→rollback) | FILLED |
| tools_search | 10 | Search pipeline (scope→regex+semantic→relevance→dedup→snippet→diff) | FILLED |
| tools_runcom | 10 | Command execution pipeline (build→optimize→env→execute→sandbox→output→timeout→error) | FILLED |
| tools_runtest | 10 | Test execution pipeline (discover→plan→optimize→execute→log→coverage→failure→flaky→fix→report) | FILLED |
| tools_terminal | 10 | Terminal I/O pipeline (session→state→command→stream→ANSI→error→filter→history→optimizer) | FILLED |
| tools_manangr | 10 | Project management pipeline (structure→dependency→impact→task→refactor→config→build→file→doc→optimizer) | FILLED |
| tools_database | 10 | Database query pipeline (connection→schema→query→transaction→executor→mapper→cache→error→migration→optimizer) | FILLED |
| tools_web | 10 | Web request pipeline (auth→request→network→rate→retry→response→content→cache→error→web_optimizer) | FILLED |
| tools_memory | 10 | Memory store pipeline (read→write→index→embedding→compress→evict→summarize→recall→consistency→optimizer) | FILLED |
| tools_browser | 10 | Headless browser pipeline (session→navigation→screenshot→dom→selector→interaction→network→cookies→captcha→error→optimizer) | FILLED |
| tools_lighthouse | 11 | Lighthouse hard-gate pipeline (session→navigation→audit→parse→performance→a11y→best-practices→seo→correction-prompt→loop-terminator→optimizer) | FILLED |
| **Total** | **196** | | **196 filled, 0 stubs** |

## Core Architecture

```
User Request → main_loop.md
  → orchestrator/router → safety-control → mutual_check → control
    → orchestrator/dispatcher → tooll_subagents/ (ReAct cycle) → tools_*
      → User Response
```

Three-circuit safety: safety-control → mutual_check → control.
Human-in-the-loop split: human_oversight.md (strategic, in control/) vs human_approval.md (tactical, in execution/).
Lazy MCP gateway: `mcp_servers/gateway.py` exposes category metadata and materializes servers only on tool invocation (token budget saver).
Headless browser: `tools_browser/headless_automation` via Playwright MCP server for dynamic pages and screenshots. Optional dependency: `runtime/requirements-browser.txt`.
Headroom context compression: optional local LLM CCR layer exposed as MCP category `headroom` (`headroom_compress`, `headroom_retrieve`, `headroom_stats`) and as `runtime/engine/headroom_client.py` with `SharedContext` for inter-agent handoffs. Integrated into `main_loop.md` context compaction, `tool_plan_selection.md`, `tool_invocation.md`, `memory_enrichment.md`, and `llm_engine.py`. Falls back to plaintext passthrough if `headroom-ai` is not installed. Optional dependency: `runtime/requirements-headroom.txt`.
Memanto semantic memory: optional active memory agent exposed as MCP category `memanto` (`memanto_create_agent`, `memanto_remember`, `memanto_recall`, `memanto_answer`) and as `runtime/engine/memanto_client.py`. Integrated into `main_loop.md` session lifecycle, `tool_plan_selection.md` recall-before-planning, `tool_invocation.md` MCP routing, and `memory_enrichment.md` long-term persistence. Falls back to in-memory store when the Memanto server is unreachable. Optional dependency: `runtime/requirements-memanto.txt`.
Mem0 long-term memory: optional hybrid semantic + keyword memory layer exposed as MCP category `mem0` (`mem0_add`, `mem0_search`, `mem0_get_all`, `mem0_delete`) and as `runtime/engine/mem0_client.py`. Integrated into `main_loop.md` session lifecycle, `tool_plan_selection.md` recall-before-planning, `tool_invocation.md` MCP routing, and `memory_enrichment.md` long-term persistence. Supports embedded local vector stores (Chroma/Qdrant) or the managed Mem0 cloud API. Falls back to in-memory store when `mem0ai` is not installed or the API is unreachable. Optional dependency: `runtime/requirements-mem0.txt`.
Lighthouse hard gate: `tools_lighthouse/audit` runs Lighthouse via Playwright, parses 500 KB reports into compact correction prompts, and enforces 100% on Performance, Accessibility, Best Practices, and SEO with a 5-iteration convergence guard. Integrated into `self_correction/result_validation.md` and `recursion_or_termination.md`.
Backend Spec Bridge: `figma-agent-core/backend_bridge.py` parses OpenAPI/Prisma/text specs, maps UI forms to backend models, and generates `prisma/schema.prisma`, `app/api/*.ts` routes, and `app/actions/*Action.ts` Server Actions. MCP category `backend` registered in `mcp_servers/backend_server.py`.
Visual QA V2: `figma-agent-core/figma_reference_downloader.py` fetches Figma reference screenshots; `figma-agent-core/visual_qa.py` runs stable Chromium (exact viewport, font/image loading wait, disabled animations), structural layout checks (overflow, clipped text, overlaps, bbox mismatch), and feeds structured reports into `figma-agent-core/refinement_loop.py` for deterministic AST adjustments.
Conditional Edges: `runtime/engine/pipeline_runner.py` uses `PhaseTransitionManager` to route between ReAct phases based on agent outputs.
Ponytail protocol: `runtime/engine/ponytail_optimizer.py` injects the 7-step Ladder of Laziness into code-generation system prompts via `ponytail_injector.md`; `ponytail_review.md` validates results for over-engineering; `ponytail_audit.md` provides repository-wide over-engineering audits on `/ponytail-audit`.
`project_rules.md` in repo root is lightweight project context loaded by the runtime; updates require human approval.

## Conventions

- **Naming**: snake_case filenames
- **Directory quirks preserved**: `tooll_subagents` (double "l"), `tools_manangr` (typo in "manager")
- **Algorithmic template** for all agents: `# Agent Name`, `## Role`, `## Contract` (Receives/Returns/Side effects), `## Decision Flow` (numbered steps), `## Failure Modes` (Condition→Response table)
- **Pipeline architecture** varies by category: linear (read), diamond (search), safety-gated (replace), sandboxed (runcom), framework-dispatch (runtest), session-stateful (terminal), analysis-planning (manangr), query-lifecycle (database), request-lifecycle (web), store-lifecycle (memory), headless-automation (browser), quality-lifecycle (lighthouse)
- **No comments** in code unless the WHY is non-obvious; deliberate Ponytail simplifications are marked with `ponytail:` comments naming the ceiling and upgrade path
- **No new files** unless the architecture requires it — prefer editing existing agents
- **Safety first** — any change to execution, control, or safety layers must respect the three-circuit flow
- **Cross-cutting optimizer** — each `tools_*` category has one strategist agent (e.g., `read_optimizer`, `project_optimizer`, `db_optimizer`) that coordinates the pipeline
- **Ponytail protocol** — code-generation agents receive the 7-step Ladder of Laziness in their system prompt (mode `lite`/`full`/`ultra`/`off`); over-engineering is reviewed in self-correction
- **Headroom protocol** — optional context compression for large tool outputs, logs, RAG chunks, and multi-agent handoffs; enabled by default via `HEADROOM_ENABLED`; safety/control/audit layers always receive uncompressed originals unless an explicit compression step is planned
- **Memanto protocol** — optional active semantic memory for durable cross-session facts; enabled via `MEMANTO_ENABLED`/`MEMANTO_URL`; degrades to in-memory fallback when the server is unavailable; safety/control/audit layers never route sensitive data through Memanto unless explicitly allowed by policy
- **Mem0 protocol** — optional hybrid semantic + keyword long-term memory for user preferences, project facts, and session context; enabled via `MEM0_ENABLED`; supports local Chroma/Qdrant (embedded) or Mem0 Cloud (`MEM0_API_KEY`); degrades to in-memory fallback when `mem0ai` is not installed or the API is unreachable; safety/control/audit layers never route sensitive data through Mem0 unless explicitly allowed by policy

## Cross-Session Memory

Memory files live at:
`C:\Users\User\.claude\projects\D--My-head-folders-My-desktop----------Agentic-Loop\memory\`

- `MEMORY.md` — index of all memories
- `project_architecture.md` — complete architecture reference

Read memory when resuming work. Update memory when architecture changes or key decisions are made.

## Current Progress & Next Steps

1. **FILLED (196 agents)** — All layers fully implemented:
   - `main_loop.md` (1) — ReAct head agent with Lighthouse hard-gate and Headroom context-compaction integration
   - `orchestrator/` (6) — Router, dispatcher, pipeline coordinator, state manager, API gateway, message bus
   - `safety-control/` (9) — Input sanitization, permissions, threats, leaks, output review, bias, safety assessment, content checking
   - `mutual_check/` (10) — Audit, verification, consistency, validation, performance, quotas, anomalies, quality, feedback, compliance
   - `control/` (7) — File system, network, resources, human oversight, policy, scope, input aggregation
   - `tooll_subagents/` (42) — Full ReAct cycle: user→planning→execution→observability→self_correction→result, including `figma_precise_mode_auditor.md`, `backend_spec_bridge.md`, `responsive_composer.md`, `component_registry.md`, Visual QA V2 refinements in `result_validation.md`, Lighthouse convergence guard in `recursion_or_termination.md`, Ponytail protocol agents (`ponytail_injector.md`, `ponytail_review.md`, `ponytail_audit.md`), Headroom agents (`headroom_injector.md`, `headroom_compressor.md`, `headroom_retriever.md`), Memanto agents (`memanto_remember.md`, `memanto_recall.md`, `memanto_answer.md`), and Mem0 agents (`mem0_remember.md`, `mem0_recall.md`, `mem0_list.md`)
   - `tools_*` (121) — 12 categories × 10+ tool agents each with cross-cutting optimizers, including `tools_browser/headless_automation` for Playwright-based dynamic web automation and `tools_lighthouse/audit` for Lighthouse 100% hard-gate audits
2. **STUBS (0 agents)** — No remaining placeholders. All agents follow the Algorithmic template.
3. **System status**: COMPLETE — All 6 layers operational with three-circuit safety, full ReAct decomposition, lazy MCP gateway, `project_rules.md` context, headless browser tools, Lighthouse hard-gate pipeline, safe-component generation, Backend Spec Bridge, Responsive Composer, Component Registry, automatic Figma reference download, stable Chromium Visual QA, structural layout checks, conditional ReAct phase transitions, Ponytail cross-cutting optimization protocol, optional Headroom context-compression layer with reversible CCR, MCP tools, and runtime client, optional Memanto semantic-memory pipeline with MCP tools, runtime client, and ReAct integration, and optional Mem0 long-term memory pipeline with MCP tools, runtime client, local embedded vector-store support, cloud API support, and ReAct integration.

## Active Skills

/graph-pilot — Graphify codebase navigation autopilot. Translates plain-language intent
("разберись, как тут устроена авторизация") into the correct Graphify command with
token guards (never runs expensive `--mode deep` or installs breaking hooks blindly).
Skill files: `.claude/skills/graph-pilot/SKILL.md`.

/claude-api — Claude API integration skill (active behavioral directive)

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
