# Plan — Strict Token Matching for Figma Variables/Styles

## Goal
Make `design_tokens.py` and `layout_engine.py` honor Figma variable/style names exactly, producing hierarchical Tailwind tokens (e.g. `colors.primary.500` → class `bg-colors-primary-500`, CSS var `--colors-primary-500`) instead of guessing semantic names from raw hex values.

## Why
Builder.io-style fidelity requires that a Figma variable called `colors/primary/500` maps to the same token path in code, preserving the design system hierarchy and enabling round-trip updates.

## Files to change
1. `figma-agent-core/design_tokens.py`
2. `figma-agent-core/layout_engine.py`
3. `tests/figma/fixtures/tokens_explicit.json`
4. `tests/figma/test_design_tokens.py`
5. `tests/figma/test_layout_engine.py`

## Implementation steps

### 1. Normalization helpers
- Add `_safe_token_path(name: str) -> str`:
  - lowercase, strip, replace `/` with `.`, collapse whitespace and invalid chars, collapse repeated dots.
  - `colors/primary/500` → `colors.primary.500`; `color/background` → `color.background`.
- Add `_css_var_from_path(path: str) -> str`:
  - replace `.` with `-`, then `_safe_kebab` → `--colors-primary-500`.
- Update `_safe_css_var` to keep accepting slash names as before.

### 2. Resolve raw hex for each style/variable
- `_resolve_id_to_hex(nodes, styles_map, variables_map)` scans every node and records the hex color observed alongside each `styles.{fill,stroke,text}` and `boundVariables.{fill,stroke,text}` ID.
- Also read variable meta `value`/`resolvedValue` if it is already a color.

### 3. Extract exact tokens first
- New method `_extract_exact_variable_color_tokens(...)`:
  - For every variable/style with a `name` and resolved hex, create a `ColorToken`.
  - Token `name` = dotted path.
  - `css_var` = `--<dashed-path>`.
  - `source` = `"variable"` or `"style"`.
  - Returns `(tokens, variable_token_map, style_token_map)` where the maps are `figma_id -> dotted_path`.
- In `extract()`, run this **before** the heuristic `_assign_color_tokens`, and merge the exact tokens into `registry.colors`.
- Keep existing heuristic assignment for unbound raw colors (backward compatibility for fixtures without variables).

### 4. Tailwind config nesting
- `generate_tailwind_config` builds a nested color object for dotted token names:
  - `colors.primary.500` → `theme.extend.colors["colors"]["primary"]["500"] = "var(--colors-primary-500")`.
  - Flat semantic tokens keep current special handling (`background`, `foreground`, `border`, etc.).

### 5. Globals CSS
- `generate_globals_css` already emits `token.css_var`; with dotted names it will produce `--colors-primary-500: #...;`.

### 6. Layout engine class generation
- In `_class_for_color`, after fetching the token name from style/variable maps, convert any `.` in the name to `-` for the Tailwind class:
  - `bg-colors.primary.500` is invalid; `bg-colors-primary-500` is correct.
- Order of lookup remains: exact style/variable maps → semantic map → hex fallback.

### 7. Registry serialization
- `TokenRegistry.to_dict()` and `save_registry()` already include `style_token_map` / `variable_token_map`; values will now be dotted paths.
- Add a top-level `exact_token_paths` list to the saved JSON for quick inspection.

### 8. Tests
- Update `tokens_explicit.json` style names to `colors/background`, `colors/foreground`, etc.
- Update `test_explicit_styles_override_heuristics` to assert exact tokens (`colors.background`, `colors.foreground`, …).
- Add tests:
  - `test_extract_exact_variable_color_tokens`
  - `test_extract_exact_style_color_tokens`
  - `test_exact_tokens_generate_nested_tailwind_config`
  - `test_exact_variable_token_map_written_to_registry`
- Add layout-engine test: node with `boundVariables.fill` and a variable path maps to `bg-colors-primary-500`.

## Validation
- Run `pytest tests/figma/test_design_tokens.py tests/figma/test_layout_engine.py`.
- Run full `pytest tests/figma` and `pytest tests/backend`.
- Run validators if available.
- Run `graphify update .` to refresh the knowledge graph.

## Risks and mitigations
- **Breaking existing semantic tests**: mitigated by keeping heuristic assignment for unbound colors and only switching bound styles/variables to exact paths.
- **Invalid nested Tailwind keys**: ensure only names containing `.` are nested; flat semantic names stay flat.
- **Variables without resolved hex**: skip them; they will fall back to raw color heuristic.

## Approval needed
Permission to modify the listed files and run tests/validators/graphify.
