# Plan — Pixel-Perfect Refinement Loop

## Goal
Strengthen Visual QA V2 and the refinement loop to achieve per-node pixel fidelity: exact DOM↔Figma node matching, per-text font metrics comparison, structural layout diff with 2 px auto-correction, and a snug-text fixer.

## Files to change
1. `figma-agent-core/layout_engine.py` — capture source Figma bbox per TailwindNode and emit it in AST.
2. `figma-agent-core/page_composer.py` — emit `data-figma-id` on every generated DOM element (already started).
3. `figma-agent-core/visual_qa.py` — improve per-node bbox matching, add font metric diff, structural layout diff.
4. `figma-agent-core/refinement_loop.py` — apply deterministic AST fixes for bbox mismatch and snug text.
5. `tests/figma/test_visual_qa.py` — update/extend mocks for new checks.
6. `tests/figma/test_refinement_loop.py` — add tests for new auto-correction types.
7. `tests/figma/test_layout_engine.py` — assert `bbox` and `data-figma-id` plumbing if tested through compose.
8. `tests/figma/test_page_composer.py` — assert `data-figma-id` output.

## Implementation steps

### 1. Per-node bbox extraction (`layout_engine.py`)
- `TailwindNode.bbox: Optional[Dict[str, float]]` already added; ensure it is populated from both `node.get("box")` and `node.get("absoluteBoundingBox")` fallback.
- `to_dict()` already includes `bbox` when present.

### 2. `data-figma-id` in generated JSX (`page_composer.py`)
- A `data_attr` string is already added to most rendering branches.
- Verify all non-component branches include it: input, textarea, select, img, inline SVG wrapper, rich-text container, children container, text-only tags, self-closing tags.
- Components receive their own DOM tree, so `data-figma-id` on component wrapper is acceptable but not required; leave a comment explaining this.

### 3. Per-node bbox matching (`visual_qa.py`)
- Change `_compare_bboxes` DOM collection to query **all** elements with `data-figma-id`, not just structural tags. Fallback to structural tags only if no `data-figma-id` elements exist (backward compatibility).
- Add a per-node `bbox_id` to match by `figma_id` first; if mismatch > tolerance, record the check.
- Rename tolerance semantics: `DEFAULT_BBOX_TOLERANCE_PX` stays 8, but the refinement loop will react when mismatch > 2 px.

### 4. Font metric diff (`visual_qa.py`)
- Replace/extend `_collect_font_metrics` with `_collect_text_metrics(page, figma_text_nodes)`:
  - Walk DOM text nodes (or query `[data-figma-id]` text containers).
  - For each node with `data-figma-id`, read computed `font-family`, `font-size`, `line-height`, `letter-spacing`, `font-weight`.
  - Compare to the matching Figma text node (passed in `figma_bboxes` or a new `figma_text_nodes` argument).
  - Emit `font_mismatch` layout checks with `delta_size_px`, `delta_line_height`, `delta_letter_spacing`, `delta_weight`.
- Keep old `_collect_font_metrics` summary (global font families) for backward compatibility, but the report will also include `font_metrics.per_node`.

### 5. Structural layout diff (`visual_qa.py`)
- The existing `_compare_bboxes` already computes `bbox_mismatch` checks with deltas.
- Ensure each mismatch carries `figma_id`, exact page and figma boxes, and deltas.
- Add `tight_bboxes` flag to the report: list of nodes where page box is larger than Figma box by > tolerance (likely a snug-text candidate).

### 6. Snug text fixer
- In `layout_engine.py`, add `_apply_text_snug_fit(tw_node, node)`:
  - For TEXT nodes, compare `node["box"]` width/height with the expected text dimensions if available. Since we don't have a text-renderer, use a heuristic:
    - If the node's horizontal sizing is `HUG` and the bbox width is much larger than a rough character count estimate, mark `needs_max_w`.
  - Add classes based on context:
    - If parent layoutMode is HORIZONTAL and text is a single line, add `whitespace-nowrap`.
    - Otherwise, add `max-w-[{figma_width}px]`.
  - Store a flag `text_snug_fit` in the AST node.
- In `visual_qa.py`, detect when a text DOM node's width is > Figma width + 4 px; emit `snug_text` layout check.
- In `refinement_loop.py`, handle `snug_text` check:
  - If `whitespace-nowrap` is appropriate (single-line, horizontal context), add it.
  - Else add `max-w-[{figma_width}px]`.

### 7. Refinement loop auto-correction (`refinement_loop.py`)
- In `_apply_layout_adjustments` extend `bbox_mismatch` handler to use the new 2 px threshold for exact-size replacement (already > 2 logic present; tighten when needed).
- Add handler for `font_mismatch`:
  - If delta size, patch `font_size` class or inline style.
  - If line-height, patch `leading-*` class.
  - If letter-spacing, patch arbitrary tracking.
  - If weight, patch `font-*` class.
- Add handler for `snug_text` as described above.
- Convergence guard already exists; it will catch stagnation after new fixes.

### 8. Tests
- `test_page_composer.py`: add `test_compose_emits_data_figma_id` and `test_compose_preserves_figma_id_on_nested`.
- `test_visual_qa.py`: add `test_visual_qa_collects_per_node_font_metrics` and `test_visual_qa_bbox_uses_data_figma_id` (mock DOM elements with dataset).
- `test_refinement_loop.py`: add `test_font_mismatch_adjusts_classes`, `test_snug_text_adjusts_max_w`.
- `test_layout_engine.py`: add `test_text_node_records_bbox`.

## Validation
- `pytest tests/figma/test_visual_qa.py tests/figma/test_refinement_loop.py tests/figma/test_page_composer.py tests/figma/test_layout_engine.py`
- `pytest tests/figma tests/backend`
- `node scripts/safety_check.js ...` on changed files
- `graphify update .`

## Risks and mitigations
- **Mock brittleness**: Visual QA relies on `page.evaluate.side_effect`; adding new evaluate calls changes the call order. Tests must be updated to include new evaluate return values.
- **`data-figma-id` on form inputs / self-closing tags**: JSX supports it fine; HTML serialization is handled by React.
- **Font metrics from computed style are strings**: parse px/rem numerically; rem values need root font-size. Keep comparison tolerant (±1 px, ±0.05 line-height).

## Approval needed
Permission to modify the listed files and run tests/validators/graphify.
