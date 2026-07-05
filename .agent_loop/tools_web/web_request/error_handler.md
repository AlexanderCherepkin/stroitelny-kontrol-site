# Error Handler

## Role
Handles HTTP errors — classifies, diagnoses, and suggests recovery actions for any web request failure. Translates network and protocol errors into actionable insights.

## Contract
- **Receives**: `{ error: { type: "network"|"http"|"tls"|"parse"|"timeout", code?: string, message: string, request: RequestConfig, response?: ResponseInfo } }`
- **Returns**: `{ classification: ErrorClass, severity: Severity, explanation: string, recovery: RecoveryAction[], is_retryable: bool }`
- **Side effects**: none (pure analysis)

## Decision Flow

1. **Classify network errors**
   - `ECONNREFUSED`: server actively rejecting → wrong port? firewall? service down?
   - `ENOTFOUND` / `EAI_AGAIN`: DNS failure → hostname typo? DNS server unreachable?
   - `ECONNRESET`: connection reset mid-transfer → server crash? proxy timeout?
   - `ETIMEDOUT`: no response within timeout → server overloaded? network congestion? dead server?
   - `EPIPE`: write to closed connection → server closed before request completed
   - `EHOSTUNREACH`: no route to host → VPN required? network misconfiguration?

2. **Classify TLS errors**
   - `CERT_HAS_EXPIRED`: certificate past expiry date → server misconfiguration
   - `CERT_COMMON_NAME_INVALID`: CN/SAN mismatch → wrong hostname? misconfigured cert?
   - `SELF_SIGNED_CERT`: self-signed, not in trust chain → dev environment? man-in-the-middle?
   - `UNABLE_TO_VERIFY_LEAF_SIGNATURE`: intermediate cert missing → incomplete chain on server
   - `DEPTH_ZERO_SELF_SIGNED_CERT`: self-signed root → internal/self-managed CA
   - `SSL_VERSION_INTERFERENCE`: TLS version mismatch → outdated server or client

3. **Classify HTTP errors (4xx, 5xx)**
   - Already covered in response_parser for status codes
   - Synthesize: HTTP status + response body error message → unified diagnosis
   - Rate limiting: 429 + Retry-After → calculate wait, suggest backoff strategy
   - Auth failures: 401 → token expired? wrong scope? 403 → insufficient permissions

4. **Generate recovery actions**
   - DNS failure → check hostname, try alternate DNS, flush DNS cache
   - Connection refused → verify port, check firewall, verify service is running
   - Timeout → increase timeout, check network latency, try different region
   - TLS error → check system time (clock skew), verify CA bundle, check cert expiry
   - 429 Rate limit → respect Retry-After, reduce concurrency, check rate limit quota
   - 5xx Server error → retry with backoff (via retry_manager), check service status page
   - Rank actions: simplest first, escalating complexity

5. **Severity assessment**
   - `critical`: TLS cert expired, all servers unreachable → alert on-call
   - `error`: 5xx, timeout, connection refused → retry or fail gracefully
   - `warning`: 4xx (not 429), slow response → log for review
   - `info`: redirects, deprecation notices → informational

## Failure Modes
| Condition | Response |
|---|---|
| Unknown error code | Report raw error, classify as unknown network error, suggest verbose logging |
| Error chain (wrapped errors) | Unwrap and analyze each layer, report root cause |
| Proxy error (502 from proxy, not origin) | Distinguish proxy vs origin errors, suggest checking proxy configuration |
| Mixed IPv4/IPv6 failure | Report dual-stack status, suggest forcing one protocol for diagnosis |
| Too many error sources to isolate | Report aggregate, suggest reproducing with single-target test |
