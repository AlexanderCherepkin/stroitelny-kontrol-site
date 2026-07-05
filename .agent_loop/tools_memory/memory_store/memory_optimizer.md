# Memory Optimizer

## Role
Optimizes memory store performance — storage efficiency, retrieval speed, index tuning, and memory health analytics. The continuous improvement engine for the memory subsystem.

## Contract
- **Receives**: `{ target: "storage"|"retrieval"|"index"|"health"|"full", baseline?: Metrics, budget?: { max_storage_mb, max_latency_ms } }`
- **Returns**: `{ optimizations: Optimization[], before: Metrics, after: Metrics, savings: { storage_mb, latency_ms, index_size_mb }, health_score: int }`
- **Side effects**: may rewrite memory files, rebuild indexes, update configurations

## Decision Flow

1. **Storage optimization**
   - Compression: compress bodies >1KB (gzip, zstd) — store compressed, decompress on read
   - Deduplication: merge exact and near-duplicate entries
   - Archival: move entries not accessed in >90 days to cold storage
   - Frontmatter trimming: remove unused metadata fields
   - File consolidation: merge small single-entry files if they share tags/type
   - Format normalization: consistent indentation, line endings, encoding (UTF-8)

2. **Retrieval speed optimization**
   - Profile: measure p50, p95, p99 search latency
   - Cache hot queries: in-memory LRU for top 100 queries
   - Result precomputation: precompute common filter+sort combinations
   - Lazy loading: load body text only when entry is opened (list shows title+snippet only)
   - Parallelization: split query across FTS + vector in parallel, merge results
   - Pagination optimization: keyset pagination instead of offset for deep pages
   - `recall_optimizer` tunes query expansion and personalized ranking parameters after index or compression changes

3. **Index optimization**
   - FTS fragmentation: merge B-tree segments, vacuum deleted entries
   - Vector index: compact HNSW graph, prune isolated nodes
   - Composite indexes: pre-index common filter combinations (type+tags, type+date)
   - Partial indexes: index only high-priority entries for fast critical lookups
   - Index caching: keep index metadata in memory, page data on demand
   - Auto-tuning: adjust BM25 parameters (k1, b) based on query logs
   - `summarizer` regenerates condensed views and titles when entries are merged, deduplicated, or compressed

4. **Health analytics**
   - Growth rate: entries/day, bytes/day → predict capacity exhaustion
   - Read/write ratio: dominant workload type
   - Query patterns: most frequent queries, zero-result queries, slow queries
   - Entry vitality: what fraction of entries are ever accessed?
   - Memory entropy: is the store becoming more organized or more chaotic?
   - Report: weekly health digest with trends and recommendations

5. **Apply optimizations**
   - Safe: optimizations that don't change content (compression, index rebuild)
   - Review: optimizations that change content (dedup, archival)
   - Measure: apply one optimization at a time, measure impact
   - Rollback: keep backups of modified entries for 7 days
   - Schedule: non-urgent optimizations run during idle periods

## Failure Modes
| Condition | Response |
|---|---|
| Optimization increases latency | Revert that optimization, flag as incompatible with current workload |
| Compression corrupts entry | Restore from backup, flag incompatible content type for compression |
| Dedup merges semantically different entries | Revert merge, tighten similarity threshold, flag false positive |
| Index rebuild fails mid-process | Keep old index active, retry rebuild, alert on persistent failure |
| Storage savings below measurement noise | Skip optimization, avoid unnecessary churn |
