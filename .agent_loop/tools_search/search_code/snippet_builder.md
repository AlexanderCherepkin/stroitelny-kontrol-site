# Snippet Builder

## Role
Builds readable, context-rich code snippets around each search match. A naked line number is useless — a 5-line window with highlighting makes the result immediately understandable.

## Contract
- **Receives**: `{ matches: [{ file, line, match_text }], options: { context_lines: int, highlight: bool, max_snippet_length } }`
- **Returns**: `{ snippets: [{ file, line_range, code, match_highlighted, language }], total_files }`
- **Side effects**: reads files from disk (cached where possible)

## Decision Flow

1. **Group matches by file**
   - Sort all matches by file → line
   - Within a file, merge overlapping context windows into single snippets
   - Example: match at line 10 and match at line 13 with context=3 → one snippet lines 7-16

2. **Determine context window per match**
   - `context_lines` lines before and after the match (default: 3)
   - Extend to nearest function/class boundary if detectable (better semantic context)
   - Never exceed `max_snippet_length`
   - If match is on line 1 → no before-lines; if on last line → no after-lines

3. **Read and format**
   - Read the target lines from the file (use cache when available)
   - Detect language from file extension for syntax rendering hint
   - Add line number prefix to each line
   - Mark the matching line(s) for highlighting: `▶` prefix or `>>>` gutter marker

4. **Build snippet object**
   ```
   {
     file: "src/auth/login.ts",
     line_range: "7-16",
     code: "  7: export class LoginHandler {\n  8:   async authenticate(\n▶ 9:     credentials: Credentials\n 10:   ): Promise<Token> {\n  ...",
     match_highlighted: "line 9",
     language: "typescript"
   }
   ```

5. **Handle large match sets**
   - If >20 snippets → group by file, show file header + match count per file
   - If single file with many matches → show file header + first 10 snippets + `... and N more`

## Failure Modes
| Condition | Response |
|---|---|
| File missing (deleted between search and snippet) | Return snippet with `code: "[file not found]"` and stale-file flag |
| Match line out of bounds | Clamp window to [1, file_line_count] |
| File is binary | Return `code: "[binary file]"` with match metadata only |
| Context window covers entire file | Still return (small file), note `"full file shown"` |
| Snippet contains unicode/wide chars | Preserve as-is, note encoding in metadata |
