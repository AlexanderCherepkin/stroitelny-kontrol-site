# Eviction Policy

## Role
Manages memory storage capacity — TTL expiration, LRU/LFU eviction, priority-based retention, and quota enforcement. Ensures the memory store stays within resource bounds.

## Contract
- **Receives**: `{ action: "evaluate"|"evict"|"stats"|"set_policy", policy?: EvictionPolicy, quota_mb?: int }`
- **Returns**: `{ evicted: EvictedEntry[], freed_bytes: int, remaining_bytes: int, warnings: string[] }`
- **Side effects**: deletes or archives memory entries from disk

## Decision Flow

1. **Evaluate capacity**
   - Measure: total memory store size vs quota
   - Headroom: if usage < 80% of quota → no action
   - Soft limit (80%): evaluate low-priority entries for eviction
   - Hard limit (95%): mandatory eviction until below 80%
   - Per-type quotas: user memories vs project memories vs feedback memories
   - Trend: is storage growing or shrinking? predict time-to-full

2. **TTL-based eviction**
   - Explicit TTL: entry has `ttl_ms` in metadata → expire after that duration
   - Implicit TTL: type-based defaults (project memories: 90 days, feedback: 180 days, user: 365 days)
   - Stale check: compare `expires_at` against current time
   - Grace period: expired entries marked for eviction, held 24h before delete (recoverable)
   - Renewal: if entry is accessed before expiry and TTL renewable → extend TTL

3. **Priority-based retention**
   - High priority (8–10): never auto-evict, manual deletion only
   - Medium priority (4–7): evict only when soft limit exceeded, prefer LFU within tier
   - Low priority (1–3): first candidates for eviction, prefer LRU + LFU
   - Pinned entries: explicitly marked as permanent → never evict
   - Recency bias: entries accessed in last 7 days get +2 effective priority

4. **LRU/LFU scoring**
   - LRU: time since last access — older = more evictable
   - LFU: access count — fewer accesses = more evictable
   - Combined score: `(1 / access_count) * log(1 + days_since_access)`
   - Size-weighted: larger entries penalized (evict one 50KB entry vs fifty 1KB entries)
   - Sort by score, evict lowest until quota met

5. **Safe eviction process**
   - Candidate list: generate ordered eviction candidates
   - Dependency check: is this entry referenced by other entries? → skip if referenced
   - Archive: move to archive directory instead of deleting (recoverable for 30 days)
   - Tombstone: leave tombstone marker so readers know entry was evicted
   - Index cleanup: remove from FTS and vector indexes
   - Report: what was evicted, why, how much space freed

## Failure Modes
| Condition | Response |
|---|---|
| Eviction would break [[wikilink]] references | Skip eviction for referenced entry, flag dangling reference risk |
| All entries high priority (nothing to evict) | Report quota exceeded, suggest increasing quota or downgrading priorities |
| Eviction not enough to reach target | Evict more aggressively (lower priority threshold), report insufficient capacity |
| Archive directory full | Delete oldest archived entries, report archive capacity issue |
| Entry locked (being read while evicting) | Skip, try next candidate, retry locked entry next cycle |
