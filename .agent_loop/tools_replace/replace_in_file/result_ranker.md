# Result Ranker

## Role
When pattern_matcher finds multiple candidates for replacement, Result Ranker decides which match is the most likely intended target. Orders replacement candidates by confidence so the pipeline applies edits to the right place first.

## Contract
- **Receives**: `{ matches: [{ line_start, line_end, match_text, context }], edit_intent: { old_string, new_string, surrounding_context, file_path } }`
- **Returns**: `{ ranked: [{ match, confidence_score, ranking_reasons }], top_match, ambiguous: bool }`
- **Side effects**: none (pure computation)

## Decision Flow

1. **Score each match candidate**
   - **Exact match to provided context**: +0.4. If caller provided surrounding lines → match with actual surrounding code.
   - **Structural position**: +0.2. Is the match inside the expected construct? (function, class, section)
   - **Indentation match**: +0.1. Does match indentation match `old_string` indentation?
   - **Semantic coherence**: +0.2. Does `new_string` make sense at this location? (variable scope, import placement)
   - **Recency**: +0.05. Recently modified region is more likely the intended target.
   - **Edit distance from ideal**: -0.1 per differing character in surrounding context.

2. **Compute confidence**
   - Aggregate scores per candidate
   - Normalize 0..1
   - `top_match`: highest-scoring candidate
   - `ambiguous`: true if top two candidates are within 0.1 of each other

3. **Disambiguation (if ambiguous)**
   - Return top candidates with differentiating context
   - Include `ranking_reasons` for each: why this candidate scored what it did
   - Suggest additional context the caller could provide to break the tie
   - Example: "Candidates at lines 45 and 128 are both strong matches. Specify which function (LoginHandler vs TokenRefresher) to disambiguate."

4. **Fallback (all scores < 0.3)**
   - No candidate looks right → return all with low confidence
   - Signal: "None of the matches look like the intended target"
   - The edit should NOT proceed — caller must provide better search criteria

## Failure Modes
| Condition | Response |
|---|---|
| Single match (no ranking needed) | Return match with `confidence: 1.0`, skip scoring |
| All candidates scored < 0.3 | `ambiguous: true`, recommend aborting edit |
| Top two candidates tied (score diff < 0.05) | Return both, require manual disambiguation |
| Match list is empty | Return empty, no ranking possible |
