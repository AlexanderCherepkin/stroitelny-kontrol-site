# Responsive Composer

## Role

Deterministic Figma-to-Tailwind responsive transformer. Reads a `layout_ast.json` produced by `figma-agent-core/layout_engine.py` plus the raw `figma_node.json` export, detects sibling breakpoint frames (Mobile / Tablet / Desktop / Phone / Laptop / Wide) and per-node Figma constraints (`horizontal` / `vertical` / `layoutSizingHorizontal` / `layoutSizingVertical` / `layoutGrow` / `layoutAlign` / `minWidth` / `maxWidth`), and emits an enriched `responsive_ast.json` whose nodes carry per-breakpoint Tailwind class overrides (`sm:` / `md:` / `lg:` / `xl:`) and fluid sizing utilities (`w-full` / `h-auto` / `flex-1` / `self-stretch` / `min-w-[Npx]`). Runs as the `responsive` stage in `figma-agent-core/conductor.py` between `backend_bridge` and `extract`; consumed by `page_composer.py` which merges `responsive_variants` into the final `className`.

## Contract

### Receives

- `layout_ast_file`: path to `layout_ast.json` (Tailwind AST from `FigmaLayoutEngine.convert`).
- `figma_file`: path to `figma_node.json` (raw Figma REST API export, preserves `horizontal` / `vertical` / `layoutSizing*` / `layoutGrow` / `layoutAlign` / `minWidth` / `maxWidth`).
- `output` (default `responsive_ast.json`): destination for enriched AST.
- `report` (default `responsive_report.json`): destination for diagnostics report (breakpoint map, matched nodes, class deltas, warnings).

### Returns

- `responsive_ast`: dict — same shape as `layout_ast` with a new `responsive_variants: Dict[str, List[str]]` field on each node. Empty dict = no overrides.
- `report`: dict — `{ "breakpoint_frames": {...}, "matched_nodes": N, "constraint_classes_added": N, "warnings": [...] }`.

### Side Effects

- Writes two JSON files (`responsive_ast.json`, `responsive_report.json`) to disk.
- No network calls, no LLM usage, no external state mutation. Pure deterministic transform.

## Decision Flow

1. **Load inputs** — read `layout_ast.json` and `figma_node.json`; verify both parse as JSON dicts; abort with structured error if either is missing or malformed.
2. **Detect breakpoint frames** — call `detect_breakpoint_frames(figma_root)`. Walk all top-level sibling FRAMEs of `figma_root.children`. Apply case-insensitive substring match on `name`: `mobile` / `phone` → `base`; `tablet` → `md`; `laptop` → `lg`; `desktop` / `wide` → `xl`. Multiple frames per breakpoint → first wins; warn.
3. **Empty-breakpoint short-circuit** — if `breakpoint_frames` is empty (only the implicit base), skip variant generation. Still run the constraint pass (step 4). Set `report["no_breakpoint_variants"] = true` and continue.
4. **Apply per-node constraints** — for every Figma node, call `constraint_to_classes(node)`. Merge resulting classes into the base `classes` list of the matching AST node (matched by `figma_id`). Mapping table: `horizontal: STRETCH` OR `layoutSizingHorizontal: FILL` → `w-full`; `vertical: STRETCH` OR `layoutSizingVertical: FILL` → `h-full`; `layoutSizingHorizontal: HUG` → drop `w-[Npx]`, emit `w-auto`; `layoutSizingVertical: HUG` → drop `h-[Npx]`, emit `h-auto`; `layoutGrow: 1` → `flex-1`; `layoutAlign: STRETCH` → `self-stretch`; `minWidth / maxWidth / minHeight / maxHeight` → `min-w-[Npx]` / `max-w-[Npx]` / `min-h-[Npx]` / `max-h-[Npx]`.
5. **Re-run layout engine on each non-base frame** — for each `(token, figma_node_id)` in `breakpoint_frames` where `token != "base"`, instantiate `FigmaLayoutEngine(config)` and call `.convert(node)`. Walk the resulting AST, diff each node's class list against the base AST's matching node, and store the diff under `responsive_variants[token]`. Prefix each diff class with the breakpoint token: `md:w-[768px]`, `lg:flex-row`, `xl:w-full`.
6. **Match nodes across frames** — Figma assigns different IDs to each viewport variant. Match by `(name.lower(), depth, position_among_siblings)` triple. Unmatched nodes → warn and skip variant.
7. **Write outputs** — serialize enriched AST and report. Maintain stable key ordering (`root.children` order preserved). Keep backward compat: nodes without variants get `responsive_variants = {}`.

## Failure Modes

| Condition | Response |
|---|---|
| `layout_ast.json` missing or invalid JSON | Return error `layout_ast_unreadable`; conductor logs and skips the stage (no break) |
| `figma_node.json` missing or invalid JSON | Return error `figma_file_unreadable`; conductor logs and skips the stage |
| No top-level FRAME children | Set `report["no_breakpoint_variants"] = true`; run constraint pass only; continue |
| Multiple sibling FRAMEs match the same breakpoint token (e.g., two "Mobile" frames) | First wins; record `warnings.append({"type": "duplicate_breakpoint", "token": ..., "kept_id": ..., "dropped_ids": [...]})` |
| Figma node has `layoutSizingHorizontal: FILL` but parent is not flex | Emit `w-full` regardless — Tailwind `w-full` is a width property, not flex-dependent. Document in report. |
| Figma node missing in a non-base breakpoint frame (no name match) | Skip variant for that node; record `warnings.append({"type": "unmatched_node", "figma_id": ..., "token": ...})` |
| Figma node has both fixed `w-[Npx]` (from `_apply_size`) and `layoutSizingHorizontal: FILL` | Base keeps `w-[Npx]`; `responsive_variants["base"]` (or the first non-base breakpoint where this conflict appears) overrides with `w-full` |
| AST has more nodes than any non-base frame | Tail of AST marked `responsive_variants = {}`; warn once |
| Constraint class would create a Tailwind conflict (e.g., `w-full` and `w-[375px]`) | Both are emitted; CSS cascade resolves by class order; the `responsive_variants` token prefix wins for ≥md. Documented in report. |
| Output file write fails (disk full, permission denied) | Raise `IOError` with the path; conductor catches and marks stage as failed |
