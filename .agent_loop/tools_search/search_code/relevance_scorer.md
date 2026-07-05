# Relevance Scorer

## Role
Takes raw search results from multiple searchers and assigns a unified relevance score. Decides what the user actually wants to see first.

## Contract
- **Receives**: `{ results: [{ source, file, line, match_text, score: null|number }], query_context: { original_query, query_type } }`
- **Returns**: `{ ranked: [{ file, line, match_text, score, boost_factors }], scoring_explanation }`
- **Side effects**: none (pure computation)

## Decision Flow

1. **Normalize input scores**
   - Each searcher uses its own scale → normalize to 0..1
   - Regex: normalize by match specificity (longer match → higher, specific vs generic characters)
   - Semantic: already 0..1 from cosine similarity, pass through
   - Unscored results → assign baseline 0.3

2. **Apply boosting factors**
   - **Recency**: files modified recently get +0.1 (active code is more likely relevant)
   - **Locality**: matches close to each other in the same file get +0.05
   - **Specificity**: exact symbol matches get +0.2 over substring matches
   - **Frequency**: rare tokens in the codebase get +0.1 (more discriminating)
   - **Path relevance**: file path containing query terms gets +0.1
   - **Test files**: matches in test files get -0.1 unless query mentions "test"

3. **Cross-source merging**
   - Same match (file + line) found by both regex AND semantic → boost by 0.15 (consensus)
   - Adjacent matches (same file, lines within 5 of each other) → merge into one result, boost by 0.1

4. **Deduplication prep**
   - Flag near-duplicates (same match text, different lines in same file)
   - Attach `boost_factors` to each result so pipeline knows WHY a score was assigned

5. **Sort and return**
   - Descending by final score
   - Attach `scoring_explanation`: summary of boosting decisions (for debugging)

## Failure Modes
| Condition | Response |
|---|---|
| All scores are 0 (no signal) | Return as-is with warning, let deduplicator and formatter handle |
| Single result | Return as-is (no ranking needed) |
| Results from only one searcher | Skip cross-source merging, still apply boosting |
| Score overflow/NaN | Clamp to 0..1, replace NaN with 0 |
