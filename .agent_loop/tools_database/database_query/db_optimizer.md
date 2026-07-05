# DB Optimizer

## Role
Optimizes database performance — query tuning, index recommendations, configuration tuning, and workload analysis. The performance engineering agent for the database layer.

## Contract
- **Receives**: `{ target: "query"|"index"|"config"|"workload"|"full", sql?: string, connection: ConnectionConfig, options: { duration_hours: int, sample_rate: float } }`
- **Returns**: `{ recommendations: Rec[], before_metrics: Metrics, estimated_improvement: { query_time_pct, index_size_mb }, applied: Rec[] }`
- **Side effects**: may CREATE/DROP indexes, may ALTER configuration (with approval)

## Decision Flow

1. **Query optimization**
   - Capture slow queries: from pg_stat_statements, slow_query_log, performance_schema
   - Explain plan: full EXPLAIN ANALYZE with buffers and timing
   - Detect: sequential scans on large tables (>10K rows without index)
   - Detect: nested loop on large datasets (should be hash join)
   - Detect: index not used despite WHERE on indexed column (type mismatch, function wrapping)
   - Suggest: rewritten query, new index, partial index, expression index
   - Before/after: benchmark both queries, report improvement
   - `query_builder` constructs the optimized SQL with safe parameter binding and dialect-aware syntax
   - `query_executor` runs the benchmarked queries under timeout enforcement and resource limits
   - `result_mapper` verifies the returned row shape matches the application contract after query changes

2. **Index optimization**
   - Missing indexes: foreign key columns, WHERE/JOIN/ORDER BY columns
   - Redundant indexes: A on (a,b) makes B on (a) redundant → DROP B
   - Unused indexes: zero scans in index usage stats → DROP (save write overhead)
   - Bloated indexes: dead tuples > 30% → REINDEX
   - Partial indexes: WHERE clause restricts rows → smaller, faster
   - Covering indexes: INCLUDE additional columns to avoid heap fetch
   - Index size vs benefit: estimate storage cost vs query speedup
   - `cache_manager` estimates cache invalidation impact and L1/L2 hit-rate changes for new indexes

3. **Configuration tuning**
   - Memory: shared_buffers / innodb_buffer_pool_size → 25% of system RAM
   - Work memory: work_mem / sort_buffer_size → scale with concurrent connections
   - Connections: max_connections vs available RAM per connection
   - WAL/checkpoint: checkpoint interval, WAL size for write-heavy workloads
   - Vacuum: autovacuum frequency and thresholds
   - Effective cache size: tell planner about available OS cache
   - Generate: recommended config changes with justification

4. **Workload analysis**
   - Profile over sample period: query frequency × execution time
   - Identify: hot tables (most queried), cold tables (rarely accessed)
   - Identify: peak hours and resource saturation points
   - Read/write ratio: optimize for dominant workload type
   - Connection pool utilization: min/max/avg active connections
   - Wait events: lock contention, I/O wait, CPU saturation

5. **Apply optimizations**
   - Safety check: new index → verify SELECT performance improvement
   - Safety check: DROP index → verify no query regression
   - Config change: apply, test workload, revert if degraded
   - One change at a time: measure isolated impact
   - `transaction_manager` wraps configuration changes and DDL in transactions where the engine supports it
   - `migration_helper` records applied optimizations as schema migrations for reproducible rollback
   - Rollback: keep DDL to revert indexes, keep config backup

## Failure Modes
| Condition | Response |
|---|---|
| Index creation times out (large table) | Suggest CREATE INDEX CONCURRENTLY, report estimated duration |
| DROP INDEX causes regression | Recreate index immediately, flag that index as "used" despite stats |
| Config change causes instability | Revert to previous config, report which setting caused issue |
| Workload sample unrepresentative | Flag insufficient data, extend sample period, suggest 24h minimum |
| Conflicting recommendations | Present trade-off, let user prioritize (speed vs storage vs maintenance) |
