# Caching Agent

## Role
Caches HTTP responses — ETag/Last-Modified conditional requests, response deduplication, stale-while-revalidate, and cache hierarchy. Reduces bandwidth and latency for repeated web requests.

## Contract
- **Receives**: `{ action: "get"|"set"|"invalidate"|"stats"|"warm", key: string, request?: RequestConfig, response?: ResponseData, policy?: CachePolicy }`
- **Returns**: `{ hit: bool, response?: ResponseData, age_ms: number, source: "cache"|"network", stats: CacheStats }`
- **Side effects**: writes to cache store (memory/disk)

## Decision Flow

1. **Compute cache key**
   - Method + URL: `GET https://api.example.com/users?page=1`
   - Normalize: sort query params, strip auth tokens from key, lowercase host
   - Vary header: include Vary field values in key (`Accept-Encoding: gzip` → separate cache entry)
   - Content negotiation: key includes Accept header value
   - Fingerprint: SHA256 of normalized request for storage lookup

2. **Cache lookup (before request)**
   - Check: exact key match in cache
   - Check: freshness — `age < max_age` from Cache-Control or default TTL
   - If fresh: return cached response (cache hit)
   - If stale: prepare conditional request with ETag (`If-None-Match`) or Last-Modified (`If-Modified-Since`)
   - If no cache entry: proceed with full request

3. **Cache update (after request)**
   - 200 OK: store full response with TTL from `Cache-Control: max-age` or default
   - 304 Not Modified: refresh stale entry's TTL, update headers only
   - Cache-Control directives:
     - `no-store` → do not cache
     - `no-cache` → cache but revalidate every use
     - `private` → cache for single user only
     - `public` → cache for all users
     - `max-age=N` → expire after N seconds
     - `s-maxage=N` → shared cache TTL
   - Vary: store separate entry per Vary header value
   - Heuristic: if no Cache-Control, estimate TTL as 10% of (Date − Last-Modified)

4. **Stale-while-revalidate**
   - Serve stale cache entry immediately
   - Async fetch from network in background
   - Update cache with fresh response
   - Next request gets fresh data
   - Stale limit: serve stale up to `stale-while-revalidate` or 24h max

5. **Cache invalidation**
   - Manual: invalidate specific key or pattern (`/users/*`)
   - TTL-based: auto-expire after max-age
   - LRU eviction: when cache exceeds size limit, evict least recently used
   - Mutation-triggered: POST/PUT/DELETE to a resource invalidates GET cache for that resource
   - Purge: clear entire cache for a host

6. **Cache storage tiers**
   - L1 (memory): hot entries, LRU, max 500 entries, sub-ms access
   - L2 (disk): all entries, max 10K entries, 1-5ms access
   - Shared (Redis): across instances for multi-process apps
   - Compression: compress bodies >1KB before storage

## Failure Modes
| Condition | Response |
|---|---|
| Cache storage full | Evict LRU entries, report eviction rate, suggest increasing capacity |
| Corrupted cache entry | Delete entry, fetch from network, report corruption |
| Conditional request not supported by server | Fall back to full request, cache using heuristic TTL |
| Vary header creates explosion of entries | Cap per-URL variants at 10, warn about excessive variation |
| Stale cache served for too long | Report staleness age, suggest reducing max-age or stale-while-revalidate |
