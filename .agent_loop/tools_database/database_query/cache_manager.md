# Cache Manager

## Role
Manages database query caching — result set caching, invalidation strategies, TTL management, cache warming, and multi-level cache (L1 memory, L2 Redis). Reduces database load for repeated reads.

## Contract
- **Receives**: `{ action: "get"|"set"|"invalidate"|"warm"|"stats", key: string, value?: any, ttl_ms?: int, tags?: string[] }`
- **Returns**: `{ hit: bool, data?: any, stats: CacheStats, invalidated_keys?: string[] }`
- **Side effects**: writes to cache store (memory/Redis), may evict entries

## Decision Flow

1. **Resolve cache key**
   - Normalize query: strip whitespace, lowercase keywords, sort WHERE clauses
   - Hash: SHA256 of normalized SQL + sorted param values
   - Include in key: query fingerprint + schema version (invalidate on migration)
   - Tag with: affected table names for targeted invalidation
   - Key format: `db:cache:{fingerprint}:{schema_version}`

2. **Multi-level cache strategy**
   - L1 (process memory): LRU, max 1000 entries, TTL 60s — for hot repeated queries
   - L2 (Redis/Memcached): LRU, max 10K entries, TTL 300s — shared across instances
   - L1 lookup first → on miss, L2 lookup → on miss, execute query → populate L2 → populate L1
   - Stale-while-revalidate: serve stale L1 data, async refresh from DB

3. **Set cache entry**
   - Store: serialized rows + column metadata + timestamp
   - TTL: query-specific or global default (60s)
   - Tags: table names, entity types for invalidation grouping
   - Size limit: refuse to cache result sets >10MB or >10K rows
   - Compression: compress JSON >1KB before storing

4. **Invalidation strategy**
   - Write-through: any INSERT/UPDATE/DELETE on table → invalidate all cached queries tagged with that table
   - Time-based: TTL expiration as fallback
   - Schema change: migration detected → invalidate all cached queries
   - Manual: explicit invalidation by key pattern or tag
   - Partial: detect affected rows, invalidate only overlapping result sets
   - Cascade: invalidation propagates L2 → all instance L1 caches

5. **Cache warming**
   - Identify hot queries: top-N by frequency × execution_time
   - Preload on startup: execute hot queries, populate L2, broadcast to L1
   - Schedule: refresh every TTL/2 to keep cache fresh
   - Budget: warm only up to cache size limit, prioritize most impactful

6. **Cache analytics**
   - Hit rate: L1 hits / total requests, L2 hits / L1 misses
   - Efficiency: cache size vs DB load reduction
   - Staleness: average age of served cached data
   - Eviction rate: entries evicted before TTL expiration (cache too small)
   - Per-table: most-cached tables, most-invalidated tables

## Failure Modes
| Condition | Response |
|---|---|
| Redis unreachable | Degrade to L1-only, warn, retry Redis connection periodically |
| Cache serialization error | Skip cache for that entry, execute query directly, report serialization issue |
| Cache memory pressure (L1 full) | Evict LRU entries, increase eviction rate, warn if thrashing |
| Write invalidation storm (1000 writes/s on same table) | Batch invalidations, debounce 100ms, coalesce by tag |
| Stale cache served (TTL too long) | Respect TTL, report staleness metric, suggest TTL reduction |
