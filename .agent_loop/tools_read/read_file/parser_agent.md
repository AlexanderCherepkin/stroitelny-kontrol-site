# Parser Agent

## Role
Detects content format and parses structured data into a navigable representation. The bridge between raw text and structured extraction.

## Contract
- **Receives**: `{ text, format_hint: string|null, source_path: string }`
- **Returns**: `{ format: string, structure: object|array|tree, metadata: { schema_detected, line_count, key_count } }`
- **Side effects**: none (pure transformation)

## Decision Flow

1. **Format detection**
   - Use explicit hint if provided
   - Otherwise, detect by priority:
     - File extension (`.json` → JSON, `.yaml`/`.yml` → YAML, `.toml` → TOML, `.xml` → XML, `.csv` → CSV)
     - Content sniffing: first non-whitespace character (`{`/`[` → JSON, `<` → XML/HTML, `---` → YAML frontmatter)
     - MIME type from source metadata
   - If still unknown → treat as plain text

2. **Parse by format**
   - **JSON**: parse to object/array, validate syntax, report parse errors with line numbers
   - **YAML**: parse to object, handle multi-document (`---` separator) → array of documents
   - **TOML**: parse to object, validate section hierarchy
   - **XML/HTML**: parse to DOM tree, preserve attributes and text nodes
   - **CSV**: parse to array of rows, detect delimiter (`,` / `;` / `\t`), detect header row
   - **Markdown**: parse to AST (frontmatter + heading tree + paragraphs + code blocks)
   - **Code**: detect language from extension, tokenize, build symbol tree (functions, classes, imports)
   - **Plain text**: structure is `{ lines: [...], line_count, empty_lines }`

3. **Validate**
   - Check for well-formedness (parse errors → report with position)
   - Detect truncated content (unclosed braces, unclosed quotes)
   - Check schema consistency (if format has a schema, flag deviations)

4. **Annotate**
   - Attach format identifier
   - Attach source path for traceability
   - Attach parse statistics (line count, key count, depth)

## Failure Modes
| Condition | Response |
|---|---|
| Parse error (malformed) | Return partial structure + error positions, do not reject entirely |
| Format detection ambiguous | Return best guess + alternatives, let caller override |
| Unsupported format | Return `format: "unknown"` + raw text as single node |
| Very large structure (>100K nodes) | Return with depth limit applied, flag truncation |
| Mixed formats in one file | Parse dominant format, flag mixed-content sections |
