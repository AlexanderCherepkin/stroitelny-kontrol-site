# Result Formatter

## Role
Normalizes pipeline output into the caller's expected format. The last mile of every read — no matter what happened upstream, the output is always shaped the same way.

## Contract
- **Receives**: `{ payload, format: "structured"|"markdown"|"plain"|"summary", options: { include_metadata, max_length, pretty } }`
- **Returns**: `{ output: string|object, metadata: { format, byte_length, truncated: bool } }`
- **Side effects**: none (pure transformation)

## Decision Flow

1. **Determine output shape**
   - `structured`: JSON object with `{ data, metadata, errors }` envelope
   - `markdown`: Markdown with fenced code blocks, heading hierarchy
   - `plain`: raw text, no formatting
   - `summary`: condensed version — first N lines + stats (line count, key count, size)

2. **Build envelope (structured mode)**
   ```
   {
     data: <payload content>,
     metadata: { source_path, encoding, format, read_at, byte_length },
     errors: [<non-fatal warnings from pipeline>]
   }
   ```

3. **Build presentation (markdown/plain mode)**
   - **Markdown**: wrap code in ``` fences with language tag, headings from structure, metadata as YAML frontmatter or blockquote footer
   - **Plain**: direct text passthrough, no markup
   - **Summary**: header line + stats block + first N lines + `... (N more lines)` footer

4. **Apply constraints**
   - `max_length`: truncate with `... [truncated]` marker if exceeded (never mid-word)
   - `pretty`: apply indentation (structured), consistent heading levels (markdown)
   - `include_metadata`: attach or omit source/encoding/timestamp info

5. **Final validation**
   - Is the output valid for its format? (JSON parseable, Markdown well-formed)
   - Does it fit within size constraints?
   - Set `truncated: true/false` in metadata

## Failure Modes
| Condition | Response |
|---|---|
| Payload too large for max_length | Truncate at safe boundary, set `truncated: true` |
| Circular reference in structured payload | Replace with `"[circular]"` placeholder |
| Format not supported | Fall back to `plain` mode |
| Empty payload | Return empty envelope (not null) with `byte_length: 0` |
| Binary content in payload | Base64-encode, flag in metadata, warn |
