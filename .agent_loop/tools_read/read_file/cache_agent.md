# Cache Agent

## Role
Avoids redundant filesystem reads. Serves cached content when fresh, passes through when stale or absent. Reduces I/O and speeds up repeated reads.

## Contract
- **Receives**: `{ absolute_path, encoding, cache_policy: { ttl_seconds, strategy: "mtime"|"hash"|"always-fresh" } }`
- **Returns**: `{ hit: bool, content: string|null, metadata: { cached_at, source_mtime }|null }`
- **Side effects**: may write to cache store on cache-miss pass-through (deferred)

## Decision Flow

1. **Compute cache key**
   - Hash `absolute_path + encoding` → deterministic cache key
   - Include encoding in key (same file, different encoding → different cache entry)

2. **Lookup**
   - Query cache store by key
   - No entry → cache miss, signal pass-through
   - Entry found → proceed to freshness check

3. **Freshness check**
   - Strategy `mtime`: compare cached `source_mtime` with current file mtime. Match → fresh. Different → stale.
   - Strategy `hash`: compare cached `content_hash` with current file hash. Match → fresh. Different → stale.
   - Strategy `always-fresh`: skip cache entirely, always pass through.
   - If TTL expired (even if mtime/hash unchanged) → treat as stale.

4. **Serve or pass-through**
   - Cache hit + fresh → return `{ hit: true, content, metadata }`
   - Cache miss or stale → return `{ hit: false, content: null }`
   - On pass-through: the result of the downstream pipeline will update this cache entry

5. **Eviction**
   - LRU eviction when cache store exceeds size limit
   - Invalidate entries for paths that no longer exist
   - Never evict entries younger than TTL

## Failure Modes
| Condition | Response |
|---|---|
| Cache store unreachable | Pass-through (graceful degradation) |
| Cache entry corrupted | Delete entry, pass-through |
| mtime unavailable (network FS) | Fall back to hash strategy if possible, else pass-through |
| Cache key collision | Statistically negligible with SHA-256, but verify mtime on hit |
| Concurrent write during read | mtime check catches modifications, treat as stale |
