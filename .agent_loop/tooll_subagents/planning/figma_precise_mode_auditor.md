# Figma Precise Mode Auditor

## Role

Pre-generation planning agent that audits a cached Figma document for Builder.io-style "Precise Mode" readiness. It checks whether the design file is structured tightly enough to be read as code with near-100% visual fidelity, and produces a prioritized remediation report before the Layout Engine or Component Registry run.

## Contract

### Receives
- `design_blueprint` or `design_descriptor`: from `.agent_loop/tooll_subagents/user/design_intake.md`
- `figma_file`: path to cached Figma document (`figma_node.json`)
- `node_id`: optional target node id to scope the audit
- `project_rules`: from `user/context.md`
- `mcp_gateway`: handle to `mcp_servers/gateway.py`

### Returns
- `precise_mode_readiness_report`: structured object:
  - `score`: float 0..1 — weighted readiness score
  - `status`: enum (`ready`, `needs_cleanup`, `not_ready`)
  - `checks`: list of check results:
    - `check_id`: enum (`auto_layout_coverage`, `exported_images`, `snug_text`, `overlap_intersection`, `alpha_transparency`, `viewport_realism`, `semantic_naming`, `component_sets`)
    - `passed`: bool
    - `severity`: enum (`info`, `warning`, `critical`)
    - `summary`: one-line human-readable result
    - `details`: list of affected node ids / names / metrics
    - `suggestion`: concrete fix instruction for the designer
  - `auto_fixable`: list of issues that can be fixed deterministically at generation time
  - `requires_designer`: list of issues that require returning to Figma
  - `next_phase_hint`: enum (`continue`, `warn_and_continue`, `halt_for_cleanup`)

### Side effects
- Calls `mcp_servers/figma_server.py` (`figma_analyze`) or reads `figma_node.json` directly
- May write `precise_mode_report.json` to disk inside the workspace
- Logs audit results to `audit_logger.md`

## Decision Flow

1. **Validate inputs** — ensure `figma_file` exists and parses as JSON; abort with `status=not_ready` if missing.
2. **Scope the tree** — if `node_id` provided, find that node; otherwise audit the full document.
3. **Check Auto Layout coverage** — walk all visible FRAME / COMPONENT / INSTANCE / GROUP nodes. For each container with children, verify `layoutMode` is `HORIZONTAL` or `VERTICAL`. Compute coverage ratio. Critical if < 90% of frame-like nodes are auto-laid-out; warning if < 100%.
4. **Check exported images / explicit assets** — verify every IMAGE node, VECTOR with image fill, and raster-like RECTANGLE has a non-empty `imageRef` or `exportSettings`. Flag nodes lacking explicit export.
5. **Check snug text bounding boxes** — for every TEXT node compare its bounding box width/height to the measured text dimensions using Figma's `box` / `absoluteBoundingBox`. If width exceeds text width + 12 px or height exceeds text height + 4 px, flag as loose; critical if > 30% of texts are loose.
6. **Check overlaps and intersections** — compare axis-aligned bounding boxes of visible sibling nodes. Count overlap pairs. Critical if any siblings overlap outside of mask/overlay semantics; warning if > 5 pairs.
7. **Check alpha / transparency** — inspect fills, strokes, effects, and node opacity. Count nodes with `opacity < 1.0`, alpha-channel colors, translucent gradients, or `BACKGROUND_BLUR`. Warning if present; critical if used for primary backgrounds or text.
8. **Check viewport realism** — measure the target frame's width/height. If the design is > 1.5× or < 0.5× the target viewport (e.g., 1440×900 desktop), flag scaling risk.
9. **Check semantic naming** — flag generic names (`Frame 1`, `Group`, `Vector`, `Rectangle`) and names with emoji/special characters. Critical only if a top-level section has a generic name; otherwise warning.
10. **Check component sets** — count COMPONENT_SET / COMPONENT / INSTANCE nodes. If no reusable components exist, warn that design system consistency may be low.
11. **Compute score** — weighted formula:
    - `auto_layout_coverage` 25%
    - `exported_images` 15%
    - `snug_text` 15%
    - `overlap_intersection` 15%
    - `alpha_transparency` 10%
    - `viewport_realism` 10%
    - `semantic_naming` 5%
    - `component_sets` 5%
12. **Classify status and route** —
    - `score >= 0.85` and zero critical → `ready`, `continue`
    - `score >= 0.70` and zero critical → `needs_cleanup`, `warn_and_continue`
    - score < 0.70 or any critical → `not_ready`, `halt_for_cleanup`
13. **Return** — emit `precise_mode_readiness_report` and `next_phase_hint`.

## Failure Modes

| Condition | Response |
|---|---|
| `figma_file` missing or unreadable | `status=not_ready`; log to `audit_logger.md`; `next_phase_hint=halt_for_cleanup` |
| Target `node_id` not found | Audit full document; record `warning` about scope fallback |
| All checks pass but no components found | `status=ready`; include `info` that design system mapping is optional |
| File contains only a design brief / no Figma structure | Return `status=not_ready`; route back to `user/design_intake.md` |
| Auditor itself crashes | Catch exception, return `status=not_ready` with `error` field, route to `human_oversight` |
