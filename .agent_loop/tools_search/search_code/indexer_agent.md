# Indexer Agent

## Role
Builds and maintains a search index for the project. Turns file contents into a queryable structure — word positions, symbol maps, metadata. Makes repeated searches fast.

## Contract
- **Receives**: `{ scope: { roots, include_globs, exclude_globs }, index_type: "full-text"|"symbols"|"hybrid" }`
- **Returns**: `{ index_id, stats: { file_count, token_count, build_time_ms }, ready: bool }`
- **Side effects**: writes index to disk (cache directory)

## Decision Flow

1. **Check index freshness**
   - Hash the scope definition → index identity
   - Check if a fresh index exists on disk
   - Freshness: index mtime > newest file mtime in scope, AND scope hash matches
   - If fresh → load existing index, return immediately (skip rebuild)

2. **Select index structure**
   - `full-text`: inverted word index (token → {file, positions}). Fast for keyword/regex search.
   - `symbols`: code-aware index (function_names, class_names, imports, exports). Fast for "where is X defined?"
   - `hybrid`: both. More build time, most versatile.

3. **Traverse and tokenize**
   - Walk file tree matching include/exclude globs
   - For each file: read, detect language, tokenize
   - Tokenizer per language: split identifiers (`camelCase` → `camel`, `case`), keywords, literals
   - Build inverted index: token → [{file_path, line_number, column, context_hash}]

4. **Build symbol table (if symbols/hybrid)**
   - Parse each file for definitions: functions, classes, variables, imports, exports
   - Build symbol → {file, line, kind, signature} map
   - Cross-reference: symbols that reference other symbols

5. **Store index**
   - Serialize to disk with scope hash as key
   - Compress (index is highly repetitive — gzip reduces to ~10% size)
   - Return index handle for searchers to use

## Failure Modes
| Condition | Response |
|---|---|
| Index build exceeds memory limit | Switch to batched build, process files in groups |
| File changed during build | Mark index as eventually-consistent, note files that may be stale |
| No files in scope to index | Return empty index (valid, but zero entries) |
| Index file corrupted on disk | Delete, rebuild from scratch |
| Language unknown (can't tokenize) | Fall back to whitespace tokenization |
