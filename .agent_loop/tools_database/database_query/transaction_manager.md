# Transaction Manager

## Role
Manages database transactions — begin, commit, rollback, savepoints, isolation levels, and distributed transaction coordination. Ensures ACID compliance at the application level.

## Contract
- **Receives**: `{ action: "begin"|"commit"|"rollback"|"savepoint"|"release"|"status", options: { isolation: IsolationLevel, read_only: bool, deferrable: bool }, tx_id?: string }`
- **Returns**: `{ tx_id: string, status: "active"|"committed"|"rolled_back"|"failed", savepoints: string[], duration_ms: int }`
- **Side effects**: modifies transaction state on database connection

## Decision Flow

1. **Begin transaction**
   - Set isolation level: READ COMMITTED (default), REPEATABLE READ, SERIALIZABLE, READ UNCOMMITTED
   - Set mode: READ WRITE (default), READ ONLY
   - Set deferrable: DEFERRABLE (wait for lock) or NOT DEFERRABLE (fail fast)
   - Acquire connection from pool, pin to transaction
   - Return transaction handle with unique ID
   - Timeout: set idle_in_transaction timeout to prevent hanging transactions

2. **Execute within transaction**
   - All queries in transaction context go through same pinned connection
   - Track: queries executed, rows affected, savepoints created
   - Nested transaction support: BEGIN → SAVEPOINT sp1 → SAVEPOINT sp2
   - Advisory locks within transaction: acquire, hold until commit, auto-release on rollback
   - Detect: transaction idle > 60s → warn, > 300s → escalate

3. **Savepoint management**
   - Create: `SAVEPOINT sp_name` — named checkpoint within transaction
   - Rollback to: `ROLLBACK TO SAVEPOINT sp_name` — partial undo
   - Release: `RELEASE SAVEPOINT sp_name` — merge savepoint into parent
   - Nesting: savepoints can nest arbitrarily deep
   - After savepoint rollback: transaction continues, earlier savepoints still valid

4. **Commit**
   - Pre-commit validation: all constraints satisfied, no deferred checks pending
   - Flush: send COMMIT, wait for acknowledgement
   - On success: release advisory locks, return connection to pool, clear transaction context
   - On conflict: serialize COMMIT attempts, retry on serialization failure (SERIALIZABLE)
   - Post-commit hooks: cache invalidation, event emission, outbox processing

5. **Rollback**
   - Explicit rollback: user-initiated, clean undo
   - Error-triggered: any query error marks transaction as failed
   - Failed transaction: must rollback, cannot commit
   - Full rollback: ROLLBACK, release all savepoints, return connection to pool
   - Partial rollback: ROLLBACK TO SAVEPOINT — transaction continues

6. **Distributed transactions (multi-DB)**
   - Two-phase commit: PREPARE all participants → COMMIT all (or ROLLBACK all)
   - Coordinator: track all participant transaction IDs
   - Failure in Phase 1 (prepare): ROLLBACK all
   - Failure in Phase 2 (commit): COMMIT succeeded participants, flag in-doubt transactions
   - Timeout: heuristic rollback after coordinator timeout

## Failure Modes
| Condition | Response |
|---|---|
| Transaction idle timeout | Rollback, release connection, report abandoned transaction |
| Serialization failure at commit | Retry entire transaction up to 3 times, fail if persists |
| Deadlock in transaction | Rollback to last savepoint or full rollback, report deadlock participants |
| Connection lost mid-transaction | Rollback (server auto-rollbacks), report connection failure |
| Commit fails (disk full, quota exceeded) | Rollback, report resource issue, escalate |
| Distributed participant unreachable | Mark in-doubt, log for manual resolution, continue with available |
