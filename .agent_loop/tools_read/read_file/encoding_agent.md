# Encoding Agent

## Role
Detects character encoding and converts raw bytes to workable text. Ensures the pipeline never operates on garbled content.

## Contract
- **Receives**: `{ raw_bytes, encoding_hint: string|null, content_type: string|null }`
- **Returns**: `{ text: string, encoding: string, confidence: 0..1, has_bom: bool }`
- **Side effects**: none (pure transformation)

## Decision Flow

1. **Check for BOM**
   - UTF-8 BOM: `EF BB BF` → encoding confirmed, strip BOM from output
   - UTF-16 LE BOM: `FF FE` → encoding confirmed
   - UTF-16 BE BOM: `FE FF` → encoding confirmed
   - UTF-32 BOM: `FF FE 00 00` (LE) or `00 00 FE FF` (BE) → encoding confirmed
   - No BOM → proceed to hint or detection

2. **Use explicit hint if provided**
   - Hint from: HTTP `Content-Type` header, file metadata, user specification
   - Try decoding with hinted encoding
   - If successful → return with high confidence (0.95)
   - If decoding fails → ignore hint, proceed to detection

3. **Auto-detect encoding**
   - Sample first 4 KB of bytes (enough for statistical analysis)
   - Test candidates in order: UTF-8 → UTF-16 LE/BE → Latin-1 → Windows-1252 → Shift-JIS → GBK → UTF-32
   - UTF-8 validation: check byte sequence validity, count invalid sequences
   - For each candidate: decode sample, score by character validity and language model
   - Select highest-scoring candidate

4. **Binary file detection**
   - If >30% of sampled bytes are control characters (excluding whitespace, tabs, newlines) → flag as binary
   - Return `text: null, encoding: "binary"` — pipeline stops here

5. **Full decode**
   - Decode entire byte array with selected encoding
   - Handle replacement characters for truly undecodable bytes
   - Return complete text + encoding metadata

## Failure Modes
| Condition | Response |
|---|---|
| No encoding matches with confidence > 0.5 | Return with `confidence` score, let caller decide |
| Binary file detected | Return `encoding: "binary"`, pipeline must not parse |
| Mixed encoding in one file | Decode with best match, flag in metadata |
| Encoding not supported by system | Return error + list of supported encodings |
| Input is already text (not bytes) | Pass through unchanged, report `encoding: "passthrough"` |
