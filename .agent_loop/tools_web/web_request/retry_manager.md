# Retry Manager

## Role
Manages request retries — exponential backoff, jitter, circuit breaker, and retry budget. Decides whether, when, and how to retry a failed HTTP request.

## Contract
- **Receives**: `{ request: RequestConfig, response?: ResponseInfo, error?: ErrorInfo, attempt: int, policy: RetryPolicy }`
- **Returns**: `{ should_retry: bool, wait_ms?: int, reason?: string, next_attempt: int }`
- **Side effects**: none (pure decision)

## Decision Flow

1. **Classify failure type**
   - Network error: DNS failure, TCP timeout, TLS error, connection refused → retryable
   - Timeout: connect timeout, read timeout → retryable
   - Server error: 500, 502, 503, 504 → retryable (server may recover)
   - Rate limit: 429 Too Many Requests → retryable after Retry-After
   - Conflict: 409 Conflict → retryable if idempotent (GET, PUT, DELETE)
   - Client error: 400, 401, 403, 404, 422 → NOT retryable (same request will fail again)
   - Redirect loop: 3xx cycle → NOT retryable

2. **Check retry conditions**
   - Idempotency: GET, HEAD, OPTIONS, PUT (same payload) → safe to retry
   - Non-idempotent: POST, PATCH → retry only if explicitly allowed (risk of duplicate creation)
   - Attempts: max 3 retries by default (configurable)
   - Budget: total retry time budget (e.g., 60s total across all retries)
   - Circuit breaker: if failure rate > 50% over last 30s → open circuit, stop retrying

3. **Calculate backoff**
   - Exponential: `base_delay * 2^(attempt-1)` — 1s, 2s, 4s, 8s
   - Jitter: multiply by random(0.5, 1.5) to spread out thundering herd
   - Cap: maximum delay 60s
   - Retry-After header: if present, use server-provided delay instead of computed
   - Total budget check: accumulated wait + next delay < retry budget? → retry; → give up

4. **Pre-retry actions**
   - Connection: may need to re-establish connection (keep-alive may have expired)
   - Auth: if 401 on retry, try refreshing token first
   - DNS: if DNS failure, re-resolve (IP may have changed)
   - Log: record attempt number, reason, wait time

5. **Give up**
   - Max attempts reached
   - Retry budget exhausted
   - Circuit breaker open
   - Non-retryable error
   - Return: final error with attempt history for diagnostics

## Failure Modes
| Condition | Response |
|---|---|
| All endpoints of load-balanced service failing | Give up after max attempts, suggest checking service health |
| Retry loop (retrying same error indefinitely) | Enforce max attempts, detect identical error pattern |
| Retry-After header unreasonably long (>1h) | Cap at 5min, report long wait, let user decide |
| POST retry creates duplicate resource | Flag potential duplicate, suggest checking resource existence |
| Circuit breaker stuck open after service recovered | Half-open probe after 30s, close on success |
