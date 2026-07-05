# Index Manager

## Role
Manages the search index for the memory store — full-text indexing, vector indexing, index maintenance, rebuild, and optimization. Ensures memory is findable.

## Contract
- **Receives**: `{ action: "index"|"reindex"|"optimize"|"rebuild"|"stats"|"validate", scope?: string | string[], method?: "fulltext"|"vector"|"both" }`
- **Returns**: `{ status: string, stats: IndexStats, errors: IndexError[], duration_ms: int }`
- **Side effects**: modifies search index files on disk

## Decision Flow

1. **Index a memory entry**
   - Full-text: tokenize body text → inverted index → FTS5 table
   - Vector: generate embedding from text → insert into vector index (faiss, hnswlib, pgvector)
   - Metadata: index tags, type, priority, dates for filtering
   - Incremental: index single entry on write (not bulk)
   - Batch: for bulk imports, index in batches of 100 for efficiency

2. **Full-text indexing (FTS5 / Lucene)**
   - Tokenization: word boundaries, lowercase, stemming (Porter)
   - Stop words: remove common words (the, a, is, of, and) for index size
   - Trigram indexing: for substring matching and typo tolerance
   - Positional indexing: store term positions for phrase queries and proximity
   - BM25 parameters: k1 = 1.2 (term saturation), b = 0.75 (length normalization)

3. **Vector indexing**
   - Embedding model: text-embedding-3-small (1536d) or local equivalent
   - Index type: HNSW for approximate nearest neighbor (ANN) — fast at scale
   - Parameters: M = 16 (connections per node), efConstruction = 200, efSearch = 50
   - Re-index trigger: embedding model change, threshold of entries added (every 100)
   - Hybrid with FTS: pre-filter by tags/type, then ANN on filtered set

4. **Index maintenance**
   - Optimize: merge fragmented FTS segments, compact vector graph
   - Reindex: rebuild entire index from source (for consistency)
   - Vacuum: reclaim space from deleted entries (tombstones)
   - Stats: index size, entry count, average entry size, fragmentation %
   - Auto-optimize: trigger when fragmentation > 20% or every N writes

5. **Index validation**
   - Consistency check: every indexed ID exists in memory store
   - Orphan check: index entries pointing to deleted memories
   - Embedding validity: no NaN/Inf vectors, correct dimensionality
   - Query test: known queries return expected results
   - Repair: remove orphans, re-index missing entries, fix corrupted vectors

## Failure Modes
| Condition | Response |
|---|---|
| Corrupted FTS index | Auto-rebuild from source, report corruption event |
| Embedding model fails to load | Fall back to keyword-only search, flag missing embeddings |
| Vector dimension mismatch (model changed) | Full re-index required, report dimension change, re-embed all |
| Index file too large (>1GB) | Split into shards by memory type, distribute across files |
| Concurrent index write conflict | Serialize writes with file lock, queue concurrent requests |
