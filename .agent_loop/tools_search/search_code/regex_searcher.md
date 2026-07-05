# Regex Searcher

## Role
Executes pattern-based search across the scoped file set. Finds exact matches for regular expressions — the surgical tool when you know exactly what you're looking for.

## Contract
- **Receives**: `{ pattern: string, scope, index_id: string|null, options: { case_sensitive, multiline, max_results } }`
- **Returns**: `{ matches: [{ file, line, column, match_text, groups }], match_count, search_time_ms, truncated: bool }`
- **Side effects**: none (read-only, uses index if available)

## Decision Flow

1. **Validate and compile pattern**
   - Check regex syntax validity — reject invalid patterns with position info
   - Detect catastrophic backtracking patterns (nested quantifiers) — warn, apply timeout
   - Compile with flags: `case_sensitive`, `multiline` (`. ` matches newlines), `unicode`
   - Literal string that looks like regex → escape or treat as literal based on `options.literal_match`

2. **Choose search method**
   - **Indexed** (index available): consult inverted index for pattern tokens, get candidate files
   - **Full scan** (no index or pattern uses wildcards that match everything): read every file in scope
   - Index method is 10-100x faster but may miss matches if index tokenization doesn't align with pattern
   - For patterns with `.*` or very short tokens (<3 chars) → prefer full scan

3. **Execute search**
   - For each candidate file: read content, scan with compiled regex
   - Apply per-file timeout (100ms) to prevent one pathological file from blocking search
   - Collect: `{ file, line, column, match_text, groups: {...named captures} }`
   - Stop when `max_results` reached → set `truncated: true`

4. **Post-process results**
   - Sort by file path, then line number
   - If truncated → note how many files were not yet searched
   - Attach timing metadata

## Failure Modes
| Condition | Response |
|---|---|
| Invalid regex syntax | Return error + position of syntax violation |
| Pattern matches everything (e.g., `.`) | Warn + cap at max_results, flag `truncated` |
| Catastrophic backtracking detected | Apply 100ms timeout, return partial results |
| No matches found | Return empty matches, not an error |
| Search timed out on specific file | Skip file, list skipped files in metadata |
