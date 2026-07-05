# Connection Manager

## Role
Manages database connections — pooling, retry logic, credential rotation, health checks, and multi-database routing. The single abstraction over any database driver's connection lifecycle.

## Contract
- **Receives**: `{ config: ConnectionConfig, action: "connect"|"disconnect"|"health"|"rotate"|"status" }`
- **Returns**: `{ pool: PoolStats, connection: ConnInfo, health: HealthStatus, metrics: { active, idle, waiting, max, errors } }`
- **Side effects**: opens/closes network connections, modifies connection pool state

## Decision Flow

1. **Resolve connection config**
   - Direct: host, port, database, user, password
   - Connection string: parse `postgresql://user:pass@host:port/db?params`
   - Environment: read from `DATABASE_URL`, `PG*`, `MYSQL_*`, `SQLITE_PATH`
   - Secrets manager: fetch from vault, AWS Secrets Manager, GCP Secret Manager
   - SSL: detect cert requirement, validate cert chain, enforce minimum TLS version
   - Redact credentials from all logs and error messages

2. **Initialize connection pool**
   - Min connections: 1–2 to handle idle traffic
   - Max connections: scale by CPU cores, upstream limit, and concurrent workload
   - Idle timeout: close connections idle >10 minutes
   - Connection lifetime: recycle after 1 hour to prevent memory leaks
   - Queue timeout: reject after 30s in wait queue (don't hang)
   - Statement timeout: per-query timeout (10s default, configurable)

3. **Health check loop**
   - Periodic: `SELECT 1` every 30s on idle connections
   - Before borrow: validate connection is alive, recycle if dead
   - After error: mark connection as broken, remove from pool
   - Pool-level health: active/total ratio, error rate, average wait time
   - Alert: active > 80% of max, error rate > 5%, avg wait > 1s

4. **Retry and circuit breaker**
   - Transient errors: retry up to 3 times with exponential backoff (100ms, 200ms, 400ms)
   - Retryable: connection timeout, deadlock, serialization failure, too_many_connections
   - Non-retryable: syntax error, constraint violation, permission denied, data too large
   - Circuit breaker: after 10 consecutive failures, open circuit for 30s
   - Half-open: allow one probe query, close circuit on success, re-open on failure

5. **Multi-database routing**
   - Read/Write split: route SELECT to replicas, mutations to primary
   - Shard routing: hash distribution key → shard connection
   - Multi-tenant: resolve tenant → database mapping from catalog
   - Fallback: replica down → route reads to primary with degraded flag
   - Transaction affinity: once in transaction, pin all queries to same connection

6. **Credential rotation**
   - Detect: credential expiry from vault metadata or connection errors
   - Rotate: fetch new credentials, open new pool, drain old pool gracefully
   - Zero-downtime: old pool accepts existing queries, new connections use new pool
   - Rollback: if new credentials fail, keep old pool alive

## Failure Modes
| Condition | Response |
|---|---|
| Connection refused (ECONNREFUSED) | Retry with backoff, report host reachability, suggest checking firewall |
| Authentication failed | Report auth error, check credentials, do NOT log password |
| Pool exhausted (all connections in use) | Reject with clear message, suggest increasing pool size or reducing concurrency |
| SSL certificate expired | Refuse connection, report cert expiry date, suggest renewal |
| DNS resolution failure | Retry with backoff, report DNS issue, suggest IP fallback |
