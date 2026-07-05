# Query Builder

## Role
Constructs safe, optimized database queries — programmatic query generation with dialect-aware SQL, parameter binding, and injection prevention. The single entry point for building any database query regardless of SQL dialect.

## Contract
- **Receives**: `{ operation: "select"|"insert"|"update"|"delete"|"upsert"|"raw", table: string, fields: string[], conditions: Condition[], joins: Join[], dialect: "postgresql"|"mysql"|"sqlite"|"mssql"|"oracle" }`
- **Returns**: `{ sql: string, params: any[], dialect: string, explain_plan?: string }`
- **Side effects**: none (pure query construction)

## Decision Flow

1. **Validate inputs**
   - Table name: allowlist check against known tables (reject arbitrary strings)
   - Field names: allowlist check against known columns or explicit wildcard
   - Conditions: type-check operator (eq, neq, gt, lt, gte, lte, in, nin, like, ilike, is_null, is_not_null, between, exists)
   - Joins: validate target table and join columns exist
   - Reject raw SQL fragments that bypass parameterization

2. **Build query by operation**
   - `select`: SELECT columns FROM table [JOIN ...] [WHERE ...] [GROUP BY ...] [HAVING ...] [ORDER BY ...] [LIMIT/OFFSET]
   - `insert`: INSERT INTO table (cols) VALUES (params) [ON CONFLICT ...] RETURNING *
   - `update`: UPDATE table SET col=param [, ...] WHERE conditions RETURNING *
   - `delete`: DELETE FROM table WHERE conditions RETURNING *
   - `upsert`: dialect-specific MERGE / ON CONFLICT / REPLACE INTO
   - `raw`: allow pre-built parameterized SQL with explicit audit flag

3. **Apply dialect rules**
   - PostgreSQL: `$1, $2` placeholders, `::type` casts, `ILIKE`, `RETURNING`
   - MySQL: `?` placeholders, backtick quoting, `LIMIT offset, count`
   - SQLite: `?` placeholders, double-quote identifiers, no RIGHT JOIN
   - MSSQL: `@p1, @p2` placeholders, bracket quoting `[table]`, `TOP N`
   - Oracle: `:1, :2` placeholders, `ROWNUM`, no LIMIT

4. **Optimize query structure**
   - Push filters into JOIN ON clause where possible
   - Reorder conditions: indexed columns first, high-selectivity first
   - Avoid `SELECT *` unless explicitly requested — list columns
   - Limit default: cap at 1000 rows unless overridden
   - Add `EXPLAIN` prefix for plan analysis mode

5. **Parameter binding**
   - Every user value becomes a bound parameter, never string-interpolated
   - Array expansion for `IN (?, ?, ?)` with dynamic placeholder count
   - Null handling: `IS NULL` vs `= NULL` per SQL semantics
   - Type coercion: dates → ISO strings, booleans → 0/1 or TRUE/FALSE per dialect

## Failure Modes
| Condition | Response |
|---|---|
| Table not in allowlist | Reject query, return list of known tables |
| Column not found in schema | Reject query, suggest similar column names |
| Unsupported dialect | Fall back to SQL:2008 standard, warn about untested dialect |
| Condition value type mismatch | Coerce where safe, reject where ambiguous |
| Query exceeds complexity threshold | Warn, suggest breaking into sub-queries or view |
