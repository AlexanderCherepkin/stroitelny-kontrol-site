# Design to Code Planner

## Role
Handoff agent that decides what the Figma design analyst's output should become: a technical assignment fed into the normal ReAct planning/execution cycle, or a fully generated code package delivered directly to the result layer. It packages the design blueprint so the main loop can continue autonomously without human confirmation.

## Contract

### Receives
- `design_blueprint`: from `tooll_subagents/planning/figma_design_analyst.md`
- `original_request`: parsed task descriptor from `user/request.md` or `user/design_intake.md`
- `project_rules`: from `user/context.md`
- `autonomy_level`: enum (`full_auto`, `spec_only`, `confirm_each`) — default `full_auto`

### Returns
- `handoff_package`: structured object:
  - `handoff_type`: enum (`technical_assignment`, `full_code`, `mixed`)
  - `technical_assignment`: markdown spec (present when type is `technical_assignment` or `mixed`)
  - `generated_code`: list of `{ file_path, content }` (present when type is `full_code` or `mixed`), including `app/components/*.tsx` from `figma_extract_components`, `src/components/ui/*.tsx` from `figma_extract_components --generate-ui`, `component_registry.json` and dependency DAG from `figma_build_component_registry`, `tailwind.config.ts` and `app/globals.css` from `figma_extract_tokens`, `responsive_ast.json` and `responsive_report.json` from `figma_responsive_compose`, `asset_registry.json` plus files under `public/assets/figma/` from `figma_download_assets`, `interactive_ast.json` and `interactive_registry.json` from `figma_map_interactions`, backend artifacts (`prisma/schema.prisma`, `app/api/*/route.ts`, `app/actions/*Action.ts`, `backend_mapping.json`) from `backend_run_bridge`, and safe-component layer (`src/components/safe/SafeLink.tsx`, `src/components/safe/ResponsivePicture.tsx`, `src/components/safe/TouchSafeElement.tsx`)
  - `summary`: human-readable summary of what was produced
  - `next_phase_hint`: enum (`planning`, `execution`, `result`)
  - `execution_plan`: optional ordered tool plan when `handoff_type=technical_assignment`
- `confidence`: float 0.0–1.0

### Side effects
- Writes handoff metadata to session state via `state_manager.md`
- Logs decision to `audit_logger.md`

## Decision Flow

1. **Evaluate blueprint status** — if `design_blueprint.status=failed`, set `handoff_type=technical_assignment` with a diagnostic assignment and route to `planning` for replanning.
2. **Runtime fast path already executed** — if the runtime invoked `figma_run_pipeline` directly, use its output as the `design_blueprint` and proceed to packaging. Do not re-run per-stage agents unless the blueprint is incomplete.
3. **Run Backend Spec Bridge when present** — if `original_request.design_descriptor.backend_spec` exists and the fast path did not already produce backend artifacts, invoke `tooll_subagents/planning/backend_spec_bridge.md` with the spec and `design_blueprint`; merge `backend_blueprint` into the handoff package.
4. **Respect explicit output mode** — from `original_request.design_descriptor.output_mode`:
   - `technical_assignment` → package spec only, route to `planning`.
   - `full_code` → package generated code only, route to `result` (with optional post-processing in `execution`). Always include `design_tokens` artifacts (`tailwind.config.ts`, `globals.css`) and backend artifacts (`prisma/schema.prisma`, `app/api/*/route.ts`, `app/actions/*Action.ts`, `backend_mapping.json`) when present.
   - `both` → package `mixed`; route to `result` with spec included as documentation and token artifacts attached.
5. **Infer when mode is missing** —
   - If `generated_code` is non-empty and confidence high → `full_code`.
   - If only `specification` exists → `technical_assignment`.
   - If neither exists → `technical_assignment` with diagnostic content.
6. **Apply autonomy level** —
   - `full_auto`: proceed without confirmation.
   - `spec_only`: always produce `technical_assignment` even if code was generated.
   - `confirm_each`: not used in autonomous-bot mode; treated as `full_auto` and logged.
7. **Ensure safe-component layer** — when `handoff_type` is `full_code` or `mixed` and the generated code does not already contain `src/components/safe/SafeLink.tsx`, `ResponsivePicture.tsx`, and `TouchSafeElement.tsx`, inject a sub-task to generate them. These components enforce Lighthouse-friendly defaults (explicit image sizing, `rel="noopener noreferrer"`, minimum 48×48 touch targets, correct ARIA).
8. **Add Lighthouse audit gate** — insert a `tools_lighthouse/audit/` audit sub-task into the execution plan after the front-end build is runnable. Set `lighthouse_max_iterations=8` and hard target 100% across Performance, Accessibility, Best Practices, and SEO.
9. **Build execution plan for spec mode** — produce ordered tool plan: `tools_read`, `tools_replace`, `tools_runtest`, `tools_lighthouse/audit/lighthouse_optimizer.md`, etc., based on target stack inferred from blueprint.
10. **Summarize** — compose `summary` describing what was generated, the safe-component layer, and the Lighthouse hard-gate.
11. **Return** — emit `handoff_package`.

## Failure Modes

| Condition | Response |
|---|---|
| Blueprint is empty or null | Return `handoff_type=technical_assignment` with apology/diagnostic; route to `planning` |
| Both spec and code are missing | Return `handoff_type=technical_assignment` with placeholder assignment; flag `assistance_request.md` |
| Generated code file path outside workspace | Sanitize path to workspace-relative location; log to `audit_logger.md` |
| Execution plan cannot be built for target stack | Return `technical_assignment` without plan; let `tool_plan_selection.md` replan |
| Autonomy level conflicts with policy | Honor `project_rules`; default to `full_auto` if policy silent |
| Safe-component layer generation fails | Continue with standard tags but flag `needs_refinement` for Lighthouse a11y/best-practices guards |
| Lighthouse optimizer unavailable | Continue generation; set `lighthouse_status=not_applicable` in result validation |

