# Content Extractor

## Role
Extracts targeted information from parsed content. Answers "what's in this file that matters?" — from a single key to a complex query.

## Contract
- **Receives**: `{ structure, query: { type: "key_path"|"regex"|"section"|"semantic", target, options } }`
- **Returns**: `{ matches: [{ value, location, context }], match_count, query_time_ms }`
- **Side effects**: none (pure computation)

## Decision Flow

1. **Classify query type**
   - `key_path`: dotted path into structure (`config.server.host`, `dependencies.*.version`)
   - `regex`: pattern match against raw or structured text
   - `section`: named section or heading range (`## Installation` through next heading)
   - `semantic`: natural-language description of what to find ("the function that handles login")

2. **Execute by type**
   - **key_path**: traverse structure, support wildcard (`*`), array indexing (`[0]`), recursive descent (`..`)
   - **regex**: compile pattern, scan full text or targeted fields, capture groups
   - **section**: find heading/section marker, extract from marker to next marker of equal or higher level
   - **semantic**: search headings, identifiers, and docstrings for keyword matches; rank by relevance

3. **Collect matches**
   - Each match includes: `value`, `location` (path/line/byte offset), `context` (surrounding 3 lines or parent node)
   - Deduplicate overlapping matches
   - Sort by location (document order) or relevance score

4. **Handle match count**
   - 0 matches → return empty with suggestion (nearest key/heading by edit distance)
   - 1 match → return directly
   - N > 1 matches → return all, flag ambiguity
   - N > threshold (100) → return first N with pagination cursor

## Failure Modes
| Condition | Response |
|---|---|
| Key path not found | Return empty + suggest closest existing path |
| Regex doesn't compile | Return error with position of invalid syntax |
| Regex matches nothing | Return empty, no suggestion (cannot guess intent) |
| Section not found | Return list of available sections for selection |
| Structure type mismatch with query | Return error explaining expected vs actual type |
