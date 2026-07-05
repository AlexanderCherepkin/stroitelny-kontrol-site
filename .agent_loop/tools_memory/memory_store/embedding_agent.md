# Embedding Agent

## Role
Generates and manages vector embeddings for memory entries — semantic encoding, batch embedding, dimension management, and embedding quality validation. Powers semantic search across the memory store.

## Contract
- **Receives**: `{ action: "embed"|"batch_embed"|"compare"|"validate", text: string | string[], model?: string, dimensions?: int }`
- **Returns**: `{ embeddings: number[][], model: string, dimensions: int, tokens_used: int, time_ms: int }`
- **Side effects**: may call external embedding API, caches embeddings on disk

## Decision Flow

1. **Select embedding model**
   - Default: text-embedding-3-small (OpenAI, 1536d) — cost-efficient, good quality
   - High quality: text-embedding-3-large (3072d) — for critical semantic search
   - Local: all-MiniLM-L6-v2 (384d) — zero-cost, offline, lower quality
   - Selection by task: search → small; clustering → large; on-device → local
   - Model pinned per index: changing model requires full re-index

2. **Preprocess text for embedding**
   - Truncate: model max input tokens (8191 for text-embedding-3-small)
   - Chunk: split long text at paragraph boundaries, embed each chunk
   - Clean: strip irrelevant formatting, normalize whitespace
   - Enrich: prepend memory type and tags as context to improve embedding quality
   - Format: `[type: project] [tags: auth, security] {body text}`

3. **Generate embeddings**
   - Single: embed one text → one vector
   - Batch: embed up to 2048 texts in one API call (cost efficiency)
   - Retry: transient API errors → retry 3 times with backoff
   - Timeout: 30s for batch, 10s for single
   - Cache: store embedding locally keyed by text hash (SHA256) to avoid re-embedding
   - Token counting: track and report tokens consumed

4. **Post-process embeddings**
   - Normalize: L2 normalize vectors for cosine similarity via dot product
   - Dimension reduction: if requested, PCA or random projection to lower dim
   - Quantization: optional int8 quantization for storage efficiency
   - Validate: check no NaN/Inf, correct dimension count, non-zero vector
   - Store: save to vector index via index_manager

5. **Similarity comparison**
   - Cosine similarity: dot product of normalized vectors (range −1 to 1)
   - Batch similarity: N×M matrix of pairwise similarities
   - Threshold: score > 0.7 → semantically related, > 0.85 → near duplicate
   - Top-K: retrieve K nearest neighbors from index
   - Cross-type comparison: are two memories about the same topic despite different types?

## Failure Modes
| Condition | Response |
|---|---|
| Embedding API rate limited | Wait per Retry-After, reduce batch size, report rate limit |
| Text exceeds model token limit | Truncate with ellipsis marker, flag truncated content |
| Embedding API returns wrong dimensions | Reject, report dimension mismatch, suggest model check |
| All-zero embedding returned (model failure) | Reject, retry with different model or local fallback |
| Embedding cache corrupted | Invalidate cache for that hash, regenerate, report corruption |
