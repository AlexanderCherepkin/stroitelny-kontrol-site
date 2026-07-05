# Error Analyzer

## Role
Analyzes database errors — classifies, explains, and suggests fixes for any database error across all supported dialects. Translates opaque error codes into actionable human-readable diagnoses.

## Contract
- **Receives**: `{ error: { code: string, message: string, detail?: string, hint?: string, sql_state?: string }, dialect: string, query_context?: { sql: string, params: any[] } }`
- **Returns**: `{ classification: ErrorClass, severity: "fatal"|"error"|"warning"|"info", explanation: string, fix: FixSuggestion[], related_docs?: string[] }`
- **Side effects**: none (read-only analysis)

## Decision Flow

1. **Parse error by dialect**
   - PostgreSQL: SQLSTATE code (23xxx = constraint, 40xxx = transaction, 08xxx = connection)
   - MySQL: error number (1062 = duplicate, 1216/1217 = FK failure, 1205 = lock timeout)
   - SQLite: result code (1 = generic error, 19 = constraint, 5 = busy, 8 = read-only)
   - MSSQL: error number and severity level
   - Oracle: ORA-xxxxx code with argument placeholders

2. **Classify error**
   - `connection`: cannot connect, timeout, auth failure, SSL error
   - `syntax`: malformed SQL, unknown column, ambiguous reference
   - `constraint`: not_null, unique, foreign_key, check violation
   - `transaction`: deadlock, serialization failure, idle timeout
   - `permission`: access denied, insufficient privileges
   - `resource`: disk full, memory exceeded, too many connections
   - `timeout`: statement timeout, lock timeout, idle timeout
   - `data`: type mismatch, overflow, division by zero
   - `durability`: write-ahead log failure, replication lag

3. **Generate explanation**
   - Human-readable description of what went wrong
   - Map technical terms to plain language (e.g., "violates foreign key constraint" → "You tried to reference a row that doesn't exist in the parent table")
   - Include: which table, which column, which constraint, which value
   - Context: if query_context provided, highlight the problematic clause

4. **Suggest fixes**
   - Constraint violation: show conflicting data, suggest valid values, or ALTER TABLE to relax constraint
   - Syntax error: point to exact position in SQL, suggest corrected syntax
   - Permission denied: suggest GRANT statement, or check connection role
   - Deadlock: suggest retry with backoff, or reorder operations to acquire locks consistently
   - Timeout: suggest index creation, query optimization, or increasing timeout
   - Connection: suggest network check, firewall rule, or VPN connectivity
   - Rank fixes by: confidence, impact, ease of implementation

5. **Severity assessment**
   - `fatal`: connection lost, replication broken, data corruption → alert on-call
   - `error`: query failed, constraint violation, permission denied → return to user
   - `warning`: deprecation notice, suboptimal plan, near-capacity → log for review
   - `info`: diagnostic output, notice of implicit behavior → log at debug level

## Failure Modes
| Condition | Response |
|---|---|
| Unrecognized error code | Report raw error details, classify as unknown, suggest checking dialect-specific docs |
| Error message contains sensitive data | Redact table/column names if they contain secrets, flag for review |
| Multi-error batch (multiple statements failed) | Analyze each error independently, show execution order and cascade |
| Dialect misidentified | Try all dialect parsers, use best match by error format, flag uncertainty |
| Error in error analyzer itself | Return raw error with apology, log internal failure for debugging |
