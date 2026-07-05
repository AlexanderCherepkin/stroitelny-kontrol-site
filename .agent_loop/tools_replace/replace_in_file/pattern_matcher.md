# Pattern Matcher

## Role
Finds the exact text to replace in the target file. The foundation of every edit — if you can't find it, you can't change it. Must be unambiguous: one match is success, zero or many is a problem.

## Contract
- **Receives**: `{ file_path, old_string, options: { match_mode: "exact"|"first"|"all"|"regex", ignore_whitespace: bool, case_sensitive: bool } }`
- **Returns**: `{ matches: [{ line_start, line_end, col_start, col_end, match_text }], is_unique: bool, match_count }`
- **Side effects**: none (read-only)

## Decision Flow

1. **Read target file**
   - Full file read (use read pipeline caching if available)
   - Record original content hash for later integrity checks by verify_agent

2. **Execute match by mode**
   - `exact` (default): find `old_string` literally in file content. Character-by-character match.
   - `first`: like exact but return the first match if multiple exist.
   - `all`: return every occurrence. Used for batch replacements.
   - `regex`: interpret `old_string` as regex, find all matches.

3. **Whitespace handling**
   - `ignore_whitespace: true` → normalize both search string and file content (collapse spaces, trim lines) before matching
   - Critical for matching code where indentation may differ from what was provided
   - Report if whitespace normalization was needed to find a match (transparency)

4. **Uniqueness assessment**
   - 1 match → `is_unique: true`, proceed
   - 0 matches → `is_unique: false`, try fallbacks (whitespace normalization, substring search)
   - N > 1 matches → `is_unique: false`, return all matches for caller to disambiguate
   - For `all` mode: uniqueness is irrelevant, return all matches

5. **Fallback strategies (0 matches only)**
   - Try matching leading/trailing whitespace trimmed
   - Try matching with tabs converted to spaces (or vice versa)
   - Try matching each line independently → report which line(s) didn't match
   - Return closest match by edit distance with specific diff

## Failure Modes
| Condition | Response |
|---|---|
| 0 matches after all fallbacks | Return `match_count: 0` + closest-match diff for diagnosis |
| 2+ matches in `exact` mode | Return all matches, require caller to provide more context |
| File not found | Delegate to path_resolver from tools_read, return its error |
| Regex compile error | Return error with position and reason |
| Match would span entire file | Warn — likely a mistake (trying to replace whole file content) |
