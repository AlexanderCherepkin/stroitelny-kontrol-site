# Memory Writer

## Role
Writes entries to the persistent memory store — creates, updates, and deletes memory records with schema validation, deduplication, and conflict resolution. The single write path for all agent memory.

## Contract
- **Receives**: `{ action: "create"|"update"|"delete"|"upsert", type: MemoryType, data: object, metadata: { tags: string[], priority: int, ttl_ms?: int, source: string } }`
- **Returns**: `{ id: string, created_at: ISO8601, version: int, status: "created"|"updated"|"deleted"|"merged"|"rejected" }`
- **Side effects**: writes to persistent memory store on disk

## Decision Flow

1. **Validate entry**
   - Schema: validate data against memory type schema (user, feedback, project, reference)
   - Required fields: type must be valid, data must be non-empty object
   - Size limit: entry body max 64KB, reject if larger
   - Tags: normalize to lowercase, trim whitespace, max 10 tags
   - Priority: 1–10 scale, defaults to 5
   - TTL: optional auto-expiry, min 60s, max 1 year
   - Source: which agent/process wrote this entry

2. **Deduplication check**
   - Exact match: identical type + data → skip, return existing ID
   - Near-duplicate: >95% similarity by normalized content hash → merge or skip
   - Same topic, different data: tag overlap >50% + same type → flag for review, write both
   - Timestamp-based: entry within 60s of existing with same tags → likely duplicate, merge
   - Dedup strategy configurable: strict (reject), lenient (merge), permissive (allow)

3. **Conflict resolution (update/upsert)**
   - Last-write-wins: default, higher timestamp overwrites
   - Version check: optimistic concurrency — if version mismatch, reject and return current version
   - Merge: for upsert, deep-merge objects, union arrays, latest scalar wins
   - Delete marker: instead of physical delete, mark as deleted with tombstone (recoverable)
   - Conflict report: if conflict detected, return both versions for manual resolution

4. **Write to store**
   - Format: frontmatter (YAML metadata) + body (markdown)
   - Atomic write: write to temp file, fsync, rename over target
   - Index update: add to MEMORY.md index if it's a primary memory file
   - Backup: keep last version as `.bak` for rollback
   - File naming: `{type}_{slug}.md` in corresponding memory directory

5. **Post-write hooks**
   - Notify: index_manager to update search index
   - Notify: embedding_agent to generate/update embedding vector
   - Notify: eviction_policy to check TTL and capacity
   - Log: record write in audit log (id, type, action, timestamp, source)

## Failure Modes
| Condition | Response |
|---|---|
| Schema validation fails | Reject with list of validation errors, suggest corrections |
| Duplicate detected (exact) | Return existing ID with status "skipped_duplicate" |
| Version conflict on update | Reject, return current version, let caller re-attempt |
| Disk full during write | Abort, clean temp file, report storage capacity issue |
| File locked by another process | Retry 3 times with exponential backoff, fail if persists |
