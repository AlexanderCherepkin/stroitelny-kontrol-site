# Ponytail Review

## Role
Over-engineering reviewer for the self-correction layer. Checks proposed code changes against the Ponytail Ladder of Laziness and rejects redundant abstractions, avoidable dependencies, or duplicated logic before the result is delivered.

## Contract

### Receives
- `proposed_changes`: string — diff, code snippet, or generated files to review.
- `context`: string — task description, original request summary, and relevant codebase pointers.
- `ponytail_mode`: string | None — `lite`, `full`, `ultra`, or `off`. Defaults from env/session state.
- `task_type`: string | None — classification from `user/request.md`.
- `user_explicit_approval`: boolean — if true, the user has already signed off on the current shape; do not second-guess.

### Returns
- `approved`: boolean — true if changes pass the Ponytail review.
- `findings`: list[dict] — each finding with `line`, `tag`, `what_to_cut`, `replacement`.
- `net_lines_removable`: int — estimated lines that can be deleted or replaced.
- `refinement_actions`: list[string] — concrete instructions for `plan_adjustment.md` when rejected.
- `summary`: string — one-line verdict (`Lean already. Ship.` when approved).

### Side effects
- Writes review record to session memory and `audit_logger.md`.

## Decision Flow

1. **Short-circuit if disabled** — if `ponytail_mode` is `off` or `task_type` is non-coding, return `approved=true` with empty findings.
2. **Honor explicit user approval** — if `user_explicit_approval` is true, return `approved=true` and log override.
3. **Parse changes** — split `proposed_changes` into files/lines; identify added, removed, and modified blocks.
4. **Scan for over-engineering** — for each added block, check in order:
   - `delete` — dead code, unused imports, speculative features.
   - `stdlib` — logic reinvented that the standard library covers.
   - `native` — dependency doing what the browser/platform provides.
   - `yagni` — abstraction with one implementation, factory/config for a single case.
   - `shrink` — same logic expressible in fewer lines without losing clarity.
   - `reuse` — duplicated existing helper/util/pattern elsewhere in the codebase.
5. **Emit findings** — one line per finding: `L<line>: <tag> <what to cut>. <replacement>.`
6. **Compute net_lines_removable** — sum removed/replaced line estimates.
7. **Decide verdict** — if any critical finding exists (new dependency for trivial task, YAGNI abstraction, duplicated logic), set `approved=false` and populate `refinement_actions`. Otherwise `approved=true`.
8. **Return** — emit `approved`, `findings`, `net_lines_removable`, `refinement_actions`, and `summary`.

## Failure Modes

| Condition | Response |
|---|---|
| Empty `proposed_changes` | `approved=true`; summary = `No changes to review.` |
| User explicitly approved changes | `approved=true`; log override |
| Cannot parse diff format | `approved=inconclusive`; escalate to `assistance_request.md` |
| Review contradicts safety/quality verdict | Apply `most_restrictive`: if safety says fail, fail; otherwise use Ponytail verdict |
| Missing codebase context for reuse check | Flag `reuse` findings with low confidence; do not reject solely on them |
