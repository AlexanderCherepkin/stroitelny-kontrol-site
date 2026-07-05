# Integrity Checker

## Role
Validates that what was read is complete and uncorrupted. The final quality gate before results leave the pipeline.

## Contract
- **Receives**: `{ result, source_metadata: { path, size_bytes, mtime, encoding }, expected: { byte_count, chunk_count }|null }`
- **Returns**: `{ valid: bool, checks: [{ name, passed, detail }], summary: string }`
- **Side effects**: none (read-only validation)

## Decision Flow

1. **Completeness checks**
   - If `expected.byte_count` provided: does result length match expected?
   - If `expected.chunk_count` provided: are all chunks present and in order?
   - If source size known: does extracted content proportionally match the original?
   - Byte-count mismatch → flag with delta

2. **Structural integrity**
   - For JSON: is it valid? Do all braces/brackets close?
   - For YAML: is indentation consistent? No unclosed blocks?
   - For XML/HTML: do all tags close? Proper nesting?
   - For CSV: consistent column count across all rows?
   - For code: do syntax constructs complete (unclosed strings, brackets)?
   - For plain text: no mid-line truncation? Last line ends with expected terminator?

3. **Encoding artifacts**
   - Scan for replacement characters (U+FFFD) — indicates decode failures
   - Scan for mojibake patterns (runs of Latin-1 characters where UTF-8 was expected)
   - If BOM was present but encoding doesn't match → flag

4. **Chunk boundary integrity**
   - Check overlap regions for consistency between adjacent chunks
   - If chunk N's end doesn't match chunk N+1's overlap → boundary error
   - Verify no gaps in byte ranges between consecutive chunks

5. **Aggregate verdict**
   - All checks pass → `valid: true`
   - Any critical check fails → `valid: false` + detailed summary
   - Only warnings → `valid: true` with `checks[].passed: true` but warnings in detail

## Failure Modes
| Condition | Response |
|---|---|
| Byte count mismatch | `valid: false` + expected vs actual delta |
| Structural corruption | `valid: false` + position of first violation |
| Encoding artifacts found | Warning + count and positions of artifacts |
| Chunk boundary gap | `valid: false` + byte range of gap |
| Nothing to validate (empty input) | `valid: true` but note empty input |
| Source metadata missing | Run only structural + encoding checks, skip completeness |
