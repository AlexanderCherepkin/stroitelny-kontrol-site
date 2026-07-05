# Conflict Resolver

## Role
Detects and resolves edit conflicts — when two changes target the same region of a file. Prevents silent overwrites when concurrent edits collide.

## Contract
- **Receives**: `{ file_path, pending_edit: { old_string, new_string, line_range }, active_edits: [{ old_string, new_string, line_range, source }] }`
- **Returns**: `{ conflict: bool, resolution: "apply"|"reject"|"merge"|"queue", resolved_edit: { old_string, new_string }|null, explanation }`
- **Side effects**: may reorder edit queue

## Decision Flow

1. **Overlap detection**
   - Compare pending edit's line range against all active/in-progress edits
   - Exact overlap (same lines) → conflict
   - Adjacent overlap (within 5 lines) → potential conflict (semantic proximity)
   - No overlap → no conflict, pass through

2. **Conflict classification**
   - **Same-old, different-new**: two edits to same text with different replacements → hard conflict
   - **Same-old, same-new**: duplicate edit → harmless, deduplicate
   - **Adjacent-old, non-overlapping targets**: sequential edits to nearby lines → soft conflict (ordering matters)
   - **Edit-delete conflict**: one edit changes text that another edit deletes → hard conflict

3. **Resolution strategies**
   - `reject`: refuse pending edit, explain why (default for hard conflicts)
   - `queue`: hold pending edit until active edit completes, then re-evaluate
   - `merge`: combine both edits if they target non-overlapping parts of the region
   - `apply`: override — pending edit replaces active edit's changes in that region

4. **Merge logic (for soft conflicts)**
   - If edit A changes lines 10-15 and edit B changes lines 16-20 → apply in order
   - Adjust line numbers of pending edit for already-applied shifts
   - Re-validate merged result (check that combined output is still valid)

## Failure Modes
| Condition | Response |
|---|---|
| Hard conflict (same region, different changes) | Reject with conflict details, let caller manually resolve |
| Active edit list unavailable (no state tracking) | Assume no conflict, proceed (optimistic) |
| Merge produces invalid output | Reject merge, report which combination of edits is incompatible |
| Circular queue dependency (A waits for B, B waits for A) | Detect cycle, break by rejecting newer edit |
