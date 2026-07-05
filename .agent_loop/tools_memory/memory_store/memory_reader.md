# Memory Reader

## Role
Reads entries from the persistent memory store — exact lookup, semantic search, filtered listing, and relationship traversal. The single read path for all agent memory access.

## Contract
- **Receives**: `{ query: ReadQuery, type?: MemoryType, tags?: string[], sort?: "relevance"|"date"|"priority", limit?: int, offset?: int }`
- **Returns**: `{ results: MemoryEntry[], total: int, facets: FacetCounts[], search_time_ms: int }`
- **Side effects**: none (read-only)

## Decision Flow

1. **Resolve query type**
   - Exact ID: direct lookup by memory entry ID → single result or null
   - Keyword: text search across title, description, body → BM25 ranking
   - Semantic: natural language query → embeddings similarity search
   - Tag filter: match any/all tags → exact match with facet counts
   - Type filter: restrict to specific MemoryType(s)
   - Hybrid: keyword + semantic combined with reciprocal rank fusion
   - Time range: filter by created_at, updated_at window

2. **Execute search**
   - Full-text index: FTS5 (SQLite) or equivalent for keyword search
   - Vector index: approximate nearest neighbor for semantic search
   - BM25 scoring: term frequency × inverse document frequency
   - Vector scoring: cosine similarity to query embedding
   - Hybrid scoring: weighted sum or reciprocal rank fusion (RRF)
   - Faceted search: count results per type, per tag, per date bucket

3. **Resolve relationships**
   - `[[wikilink]]` references in memory body → resolve to target entry
   - Backlinks: which other entries reference this one?
   - Related entries: entries sharing tags or linked via wikilinks
   - Memory graph: one-hop neighborhood for context expansion
   - Recursive depth: configurable, default 1 hop

4. **Rank and filter**
   - Re-rank by priority: high-priority entries boosted
   - Re-rank by recency: newer entries boosted (time decay factor)
   - Deduplicate: remove entries with >90% content similarity
   - Diversity: ensure results span multiple topics (MMR — maximal marginal relevance)
   - Paginate: offset/limit with stable ordering

5. **Return enriched results**
   - Each result: id, type, title, description, created_at, updated_at, tags, priority
   - Snippet: relevant excerpt with highlighted query terms
   - Score: relevance score (0–1)
   - Facets: aggregated counts for filtering UI
   - Suggestions: "did you mean?" for typos, related queries

## Failure Modes
| Condition | Response |
|---|---|
| Memory store is empty | Return empty results with zero counts, not an error |
| Query too short (<2 chars) | Require minimum query length, suggest longer query |
| Index corrupted or missing | Fall back to linear scan, flag index for rebuild |
| Embedding model unavailable | Fall back to keyword-only search, note missing semantic results |
| Search timeout (>5s) | Return partial results with timeout flag, suggest narrower query |
