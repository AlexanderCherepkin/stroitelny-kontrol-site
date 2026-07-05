# Web Optimizer

## Role
Optimizes web requests — connection reuse, compression, request batching, prefetching, and protocol optimization. Reduces latency and bandwidth for outbound HTTP traffic.

## Contract
- **Receives**: `{ target: "connection"|"compression"|"batching"|"protocol"|"full", scope: string | string[], baseline: Metrics }`
- **Returns**: `{ optimizations: Optimization[], before: Metrics, after: Metrics, savings: { latency_pct, bandwidth_pct, request_count } }`
- **Side effects**: may modify HTTP client configuration, connection pool settings

## Decision Flow

1. **Connection optimization**
   - Keep-alive: reuse TCP connections (default: on, timeout: 30s idle)
   - Connection pooling: max connections per host (6 default, tune by concurrency)
   - HTTP/2 multiplexing: multiple concurrent requests over single connection
   - HTTP/3 (QUIC): enable if server supports (Alt-Svc header)
   - DNS pre-resolution: resolve hostnames before request
   - TCP pre-warming: pre-connect to known hosts on startup
   - Connection coalescing: same IP + same TLS cert → share connection across origins
   - `network_checker` pre-validates host reachability before warming connections

2. **Compression optimization**
   - Request body compression: gzip/deflate Content-Encoding for POST/PUT > 1KB
   - Accept-Encoding: always request gzip, deflate, brotli
   - Image format negotiation: Accept with WebP/AVIF preference
   - JSON vs protobuf: binary serialization for high-throughput endpoints
   - Decompress transparently: never expose compressed bytes to consumer
   - `caching_agent` stores compressed responses and serves them on cache hits, avoiding re-compression

3. **Request batching**
   - Detect batchable requests: multiple GETs to same host → combine
   - GraphQL: merge queries into single operation
   - REST batch endpoints: detect POST /batch, aggregate individual requests
   - Batch window: collect requests over N ms, send as batch, fan-out results
   - Batching trade-off: latency gain by parallelism vs batch window delay
   - Auto-detect: if >3 concurrent requests to same host within 50ms → batch
   - `rate_limiter` adjusts batch window sizes to respect token-bucket and sliding-window quotas

4. **Prefetching and speculation**
   - Link prefetch: `<link rel="prefetch">`, `<link rel="preload">`
   - Resource hints: dns-prefetch, preconnect, prerender
   - Predictive prefetch: based on navigation patterns (user hovers link → prefetch)
   - Stale-while-revalidate updates: prefetch soon-to-expire cache entries
   - Budget: limit prefetch bandwidth to avoid wasting resources
   - `error_handler` classifies prefetch failures so the pipeline avoids repeatedly requesting dead endpoints

5. **Protocol optimization**
   - TLS 1.3: faster handshake (1-RTT, 0-RTT for resumed), always prefer
   - TLS False Start: send data immediately after Finished message
   - OCSP Stapling: cert revocation check in handshake, no separate request
   - 0-RTT resumption: send data in first flight on reconnection
   - Certificate compression: reduce handshake size

6. **Metric validation**
   - Measure: latency (p50, p95, p99), bandwidth used, connection count
   - Before/after comparison per optimization
   - Verify correctness: same response data, same status codes
   - Rollback any optimization that regresses metrics
   - Report: optimization name, mechanism, measured improvement, confidence
   - `request_builder` replays identical requests for before/after comparison under controlled headers

## Failure Modes
| Condition | Response |
|---|---|
| HTTP/2 connection fails | Fall back to HTTP/1.1, report incompatibility |
| Compression increases CPU usage > latency savings | Disable for small payloads (<1KB), keep for large |
| Batching introduces unacceptable delay | Reduce batch window, disable for latency-sensitive endpoints |
| 0-RTT rejected by server (replay attack concern) | Retry with 1-RTT, mark endpoint as 0-RTT-unsafe |
| Prefetch wastes bandwidth on unused resources | Track prefetch hit rate, disable if < 30% utilization |
