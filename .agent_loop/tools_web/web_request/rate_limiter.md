# Rate Limiter

## Role
Enforces rate limits — token bucket, sliding window, and leaky bucket algorithms for outbound HTTP requests. Prevents API quota exhaustion and respects upstream rate limits.

## Contract
- **Receives**: `{ target: string, action: "check"|"wait"|"consume"|"reset"|"stats", tokens?: int, policy: RatePolicy }`
- **Returns**: `{ allowed: bool, remaining: int, reset_at: ISO8601, wait_ms?: int, stats: LimitStats }`
- **Side effects**: consumes capacity from rate limit bucket, may delay request

## Decision Flow

1. **Resolve rate limit policy**
   - Static: user-configured max requests per second/minute/hour
   - Dynamic: parse `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` from response headers
   - Learned: track success/failure patterns, infer optimal rate
   - Per-endpoint: different limits for different API paths
   - Global: shared budget across all endpoints to same host
   - Priority tiers: critical requests get reserved capacity

2. **Token bucket algorithm (bursty traffic)**
   - Bucket: max `capacity` tokens, refills at `rate` tokens/second
   - Check: enough tokens for request? → yes: consume & send, no: wait or reject
   - Burst: up to `capacity` tokens for short traffic spikes
   - Smooth: long-term rate never exceeds configured rate

3. **Sliding window algorithm (precise counting)**
   - Window: current time → look back `window_size` seconds
   - Count: requests in that window
   - Limit: if count >= max_requests → reject or queue
   - Precision: sub-second accuracy, no edge-of-window bursting

4. **Response header parsing**
   - Standard format: `X-RateLimit-Remaining`, `X-RateLimit-Reset` (epoch seconds)
   - GitHub: `X-RateLimit-Remaining`, `X-RateLimit-Reset`
   - Twitter: `X-Rate-Limit-Remaining`, `X-Rate-Limit-Reset`
   - Custom: configurable header name mapping
   - If remaining drops below threshold: slow down preemptively, don't wait for 429

5. **Backpressure and queuing**
   - Rate limited (429 response or preemptive): queue request
   - Retry-After header: parse seconds or HTTP-date, schedule retry
   - Queue priority: FIFO by default, critical requests skip queue
   - Queue overflow: reject oldest queued request, report dropped
   - Wait notify: report estimated wait time to caller

6. **Analytics**
   - Track: requests sent, rejected, queued, retried per target
   - Utilization: consumed / limit ratio
   - Near-exhaustion events: remaining < 10% of limit
   - Trend: is limit tightening or relaxing over time?

## Failure Modes
| Condition | Response |
|---|---|
| Rate limit headers missing | Use static policy as fallback, warn about blind rate limiting |
| Rate limit headers malformed | Fall back to static policy, report parse error |
| Queue full (too many waiting requests) | Reject with clear message, suggest reducing concurrency |
| Clock skew with server | Use server's Reset timestamp, log skew for diagnostics |
| Policy too restrictive (0 requests possible) | Report configuration error, suggest minimum rate |
