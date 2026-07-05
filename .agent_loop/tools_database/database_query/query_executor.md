# Query Executor

## Role
Executes SQL queries safely — parameterized execution, timeout enforcement, result streaming, and dialect abstraction. The only path through which SQL reaches the database.

## Contract
- **Receives**: `{ query: { sql: string, params: any[] }, connection: ConnInfo, options: { timeout_ms: int, stream: bool, explain: bool, dry_run: bool } }`
- **Returns**: `{ rows: any[], row_count: int, duration_ms: int, explain_plan?: ExplainPlan, columns: ColumnMeta[] }`
- **Side effects**: executes SQL against database (mutations possible)

## Decision Flow

1. **Pre-execution validation**
   - Check: query is parameterized (no string-interpolated values)
   - Check: operation type (SELECT, INSERT, UPDATE, DELETE, DDL) for routing
   - Check: statement does not contain multiple statements (SQL injection vector — reject by default)
   - Check: query timeout is set (enforce default if missing)
   - Dry run mode: validate + explain, but do not execute

2. **Execute with timeout**
   - Set statement_timeout / max_execution_time at session level
   - Execute: send parameterized query with bound values
   - Monitor: wall-clock timer, kill query if timeout exceeded
   - Cancel: send `pg_cancel_backend` / `KILL QUERY` on timeout
   - Capture: rows affected, result set, duration, warnings

3. **Stream large results**
   - Threshold: >1000 rows → stream with cursor instead of loading all into memory
   - Cursor: server-side cursor, fetch in batches of 500
   - Backpressure: pause fetch when consumer is slow, resume when ready
   - Memory guard: abort if single row exceeds 10MB

4. **Collect execution metadata**
   - `EXPLAIN ANALYZE`: actual plan, timing per node, rows estimated vs actual
   - Column metadata: name, data type, nullable, size
   - Timing breakdown: parse time, plan time, execute time, fetch time
   - Affected tables: extract from query plan for cache invalidation

5. **Post-execution**
   - For mutations: return affected rows + RETURNING clause data
   - For DDL: return success/failure + schema diff
   - Log: query fingerprint (normalized SQL, no values), duration, row count
   - Metrics: increment operation counter, update latency histogram

## Failure Modes
| Condition | Response |
|---|---|
| Query timeout | Cancel query, return partial results + timeout error, log slow query fingerprint |
| Deadlock detected | Retry once after random backoff (50–200ms), fail on second deadlock |
| Constraint violation (FK, unique, check) | Parse constraint name, return user-friendly error with affected columns |
| Disk full during query | Abort, report disk usage, escalate to connection_manager for health alert |
| Serialization failure (MVCC conflict) | Retry up to 3 times with exponential backoff |
| Permission denied on table | Report which table, which permission, suggest GRANT |
