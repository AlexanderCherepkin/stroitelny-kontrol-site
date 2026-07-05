# Deduplicator

## Role
Collapses duplicate and near-duplicate search results. When the same symbol appears on 50 lines, the user needs to see one representative match, not 50 clones.

## Contract
- **Receives**: `{ results: [{ file, line, match_text, score }], options: { exact_only: bool, similarity_threshold: 0..1 } }`
- **Returns**: `{ unique: [{ file, line, match_text, score, occurrences }], duplicates_removed: int }`
- **Side effects**: none (pure computation)

## Decision Flow

1. **Exact deduplication (always)**
   - Same `file + line` → keep highest-scored occurrence
   - Same `match_text` in same file, adjacent lines (±3) → keep first occurrence, count the rest
   - Track removed count for reporting

2. **Near-duplicate detection (if similarity_threshold > 0)**
   - Group results by file
   - Within each file, compare match_text using normalized edit distance
   - Normalize: lowercase, strip whitespace, remove punctuation for comparison
   - If similarity > threshold → treat as duplicate cluster
   - Keep the highest-scored result from each cluster

3. **Cluster representation**
   - Each kept result gets `occurrences: N` (how many duplicates it represents)
   - Keep the best-scored match text (not a blurry average)
   - If the cluster has one very long match and several short → prefer the long one

4. **Cross-file deduplication (optional, for large result sets)**
   - If total results > 500 after within-file dedup → apply cross-file
   - Same match_text across different files → keep the best-scored file's result
   - Flag in metadata: `cross_file_merges: N`

## Failure Modes
| Condition | Response |
|---|---|
| All results are duplicates of one match | Return single result with `occurrences: N` |
| Similarity threshold too high (0.95+) | Warn: nearly exact only, may miss semantic duplicates |
| Similarity threshold too low (<0.5) | Warn: may collapse distinct matches, suggest 0.7-0.85 |
| Empty result set | Return empty, `duplicates_removed: 0` |
