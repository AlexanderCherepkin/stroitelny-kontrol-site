
# Consistency Checker

## Role
Validates memory store consistency — detects corruption, stale entries, broken references, schema violations, and logical contradictions. The integrity watchdog for the memory system.

## Contract
- **Receives**: `{ scope: "full"|"references"|"schema"|"logical"|"duplicates", fix: bool, report_detail: "summary"|"detailed" }`
- **Returns**: `{ issues: ConsistencyIssue[], fixed: int, unfixable: int, health_score: 0-100, recommendations: string[] }`
- **Side effects**: may fix auto-fixable issues (if fix=true), may delete orphaned data

## Decision Flow

1. **Reference integrity check**
   - Wikilinks: every `[[link]]` in body → resolve to existing memory entry
   - Dangling references: link targets that don't exist → flag
   - Bidirectional: if A links to B, should B mention A? (soft check)
   - MEMORY.md index: every file referenced in index exists, every memory file referenced in index
   - Cross-file references: references between memory files resolve correctly
   - Auto-fix: remove dangling links from body, add missing entries to index

2. **Schema validation**
   - Frontmatter: YAML parseable, required fields present (name, description, metadata.type)
   - Type check: metadata.type is valid MemoryType enum value
   - Date format: all dates are ISO 8601
   - Tags: no empty tags, no duplicate tags, valid characters
   - File naming: matches convention `{descriptive-slug}.md`
   - Body: non-empty, not just whitespace
   - Auto-fix: add missing required fields with defaults, fix date formats

3. **Duplicate detection**
   - Exact content hash: SHA256 of body → same hash = duplicate
   - Near-duplicate: >90% content similarity (normalized, whitespace-insensitive)
   - Same title + same type: likely duplicate even if body differs
   - Stale duplicate: older version with lower version number
   - Auto-fix: merge duplicates (keep newest), add tombstone for removed

4. **Logical consistency**
   - Contradiction detection: entry A says "X is true", entry B says "X is false"
   - Temporal consistency: entry dated after it was referenced
   - Type consistency: feedback entry marked as type=project, or vice versa
   - Priority anomalies: low-priority entry tagged as "critical" / high-priority "optional"
   - Stale decisions: decision marked as current but superseded by newer decision
   - Auto-fix: flag only, logical issues require human judgment

5. **Health scoring**
   - 100: zero issues
   - 90–99: minor issues (missing optional fields, formatting)
   - 70–89: moderate issues (dangling references, stale entries)
   - 50–69: significant issues (duplicates, schema violations)
   - <50: critical issues (corruption, data loss risk)
   - Trend: is health score improving or declining over time?

## Failure Modes
| Condition | Response |
|---|---|
| Memory file corrupted (unreadable) | Flag as corrupted, attempt recovery from backup, mark for rebuild |
| Circular reference chain detected | Flag cycle, break at weakest link, report participants |
| Too many issues to fix automatically | Report summary, suggest manual triage, fix top-N by severity |
| Fix introduces new inconsistency | Rollback fix, report cascading issue, flag for manual resolution |
| MEMORY.md index missing | Rebuild from file listing, flag as recovered, suggest audit |
