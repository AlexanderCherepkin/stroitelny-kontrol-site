# Migration Helper

## Role
Manages database schema migrations — generate, validate, execute, rollback, and track migration history. Single authority for schema version control across all supported databases.

## Contract
- **Receives**: `{ action: "generate"|"validate"|"up"|"down"|"status"|"repair", target?: string, steps?: int, dry_run?: bool }`
- **Returns**: `{ migrations: Migration[], status: MigrationStatus, executed: MigrationResult[], pending: int, schema_diff?: DiffEntry[] }`
- **Side effects**: executes DDL against database, writes migration files to disk

## Decision Flow

1. **Schema diff (generate migration)**
   - Compare: current live schema vs desired schema (from code/migrations directory)
   - Detect: new tables, dropped tables, new columns (with default?), dropped columns, type changes, constraint changes, index changes
   - Generate: ordered DDL statements with safety checks
   - Destructive changes (DROP, type change): flag with warning, require explicit confirmation
   - Data migration: if column rename detected, generate data copy step
   - Migration naming: `YYYYMMDDHHMMSS_descriptive_name.sql`

2. **Validate migrations**
   - Idempotency: can migration be re-run without error? (IF NOT EXISTS, IF EXISTS guards)
   - Ordering: no missing migrations, no gaps in sequence
   - Checksum: stored checksum matches file content (detect tampering)
   - Down migration: every `up` migration has a valid `down` (if down migrations required)
   - Dry run: execute in transaction, rollback, report what would change
   - Lock safety: does migration acquire locks that block reads? (ALTER TABLE on large table)

3. **Execute migrations (up)**
   - Lock: acquire migration lock to prevent concurrent migration runs
   - Order: execute pending migrations in sequence, stop on first failure
   - Per migration: BEGIN → execute DDL → record in migration_history → COMMIT
   - Transactional DDL: PostgreSQL (can rollback), MySQL (implicit commit per DDL) — adapt
   - Timeout: per-migration timeout, adjustable per expected duration
   - Progress: report current migration, ETA based on past runs

4. **Rollback (down)**
   - Target: rollback to specific version or last N steps
   - Order: execute `down` migrations in reverse order
   - Irreversible: flag migrations with no down path, refuse to rollback past them
   - Data loss warning: DROP TABLE, DROP COLUMN → warn about permanent data loss
   - Partial rollback: if down migration fails, report current state (partially rolled back)

5. **Migration status and history**
   - Track: version, name, executed_at, duration, checksum, success/failure
   - Detect: drift — schema changed outside migrations (manual ALTER)
   - Repair: re-sync migration history with actual schema state
   - Baseline: mark current schema as "already applied" for existing databases
   - Squash: combine N migrations into single baseline migration for faster fresh setups

6. **Seed data management**
   - Seed files: separate from migrations, idempotent INSERT/UPDATE
   - Execution: after all migrations complete, run seed files in dependency order
   - Idempotency guard: ON CONFLICT DO NOTHING, INSERT IF NOT EXISTS

## Failure Modes
| Condition | Response |
|---|---|
| Migration lock held by another process | Wait up to 30s, then report holder PID, abort |
| Checksum mismatch (migration file changed after execution) | Halt, report tampering suspicion, suggest manual review |
| DDL not supported in transaction (MySQL implicit commit) | Execute non-transactional, mark partial state on failure, suggest repair |
| Down migration missing | Refuse rollback, mark as irreversible, suggest manual rollback |
| Concurrent migration detected (multiple instances) | Serialize via advisory lock, queue waiters, report contention |
