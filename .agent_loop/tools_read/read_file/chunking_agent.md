# Chunking Agent

## Role
Splits large content into coherent, context-preserving chunks. Every chunk must be independently useful while remaining connected to its neighbours.

## Contract
- **Receives**: `{ text, strategy: "line"|"paragraph"|"heading"|"token-count", max_chunk_size, overlap_size }`
- **Returns**: `{ chunks: [{ index, text, start_byte, end_byte, context_preview }], total_chunks }`
- **Side effects**: none (pure transformation)

## Decision Flow

1. **Size check**
   - Measure content in target unit (lines, tokens, characters — depends on strategy)
   - If content fits within `max_chunk_size` → return single chunk, exit early
   - Otherwise → proceed to splitting

2. **Select strategy**
   - `line`: split at newline boundaries. Best for logs, CSVs, line-oriented data.
   - `paragraph`: split at double-newline (`\n\n`). Best for prose, documentation, Markdown.
   - `heading`: split at Markdown headings (`^#{1,6} `). Best for structured docs, READMEs.
   - `token-count`: approximate token count (chars/4), split at sentence boundaries. Best for LLM context windows.

3. **Split at semantic boundaries**
   - Never split mid-word
   - Never split mid-sentence (prefer `. `, `! `, `? ` boundaries)
   - Never split mid-code-block (preserve ``` fences)
   - If no good boundary within 20% of max size → fall back to hard split at nearest space

4. **Add overlap**
   - Each chunk (except first) includes `overlap_size` characters from the END of previous chunk
   - Overlap is taken from the same semantic boundary (sentence/paragraph start)
   - This ensures a thought/statement that straddles the boundary appears in both chunks

5. **Annotate each chunk**
   - `index`: 0-based position in sequence
   - `start_byte` / `end_byte`: byte offsets in original text
   - `context_preview`: first 80 chars of chunk (for quick identification)

## Failure Modes
| Condition | Response |
|---|---|
| Content smaller than max size | Return single chunk (normal, not an error) |
| No semantic boundary found | Hard split at `max_chunk_size` with 50-char lookback for nearest space |
| Empty content | Return zero chunks |
| `max_chunk_size` too small for overlap | Reduce overlap to 10% of chunk size, warn |
| Chunk count exceeds reasonable limit (>10K) | Warn, recommend strategy change or larger chunk size |
