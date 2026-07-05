# Network Checker

## Role
Checks network connectivity — DNS resolution, TCP reachability, TLS health, latency measurement, and connectivity path diagnostics. The "can we even reach this server?" answering machine.

## Contract
- **Receives**: `{ target: string, checks: ("dns"|"tcp"|"tls"|"latency"|"trace"|"full")[], port?: int, timeout_ms?: int }`
- **Returns**: `{ reachable: bool, checks: CheckResult[], latency: { min, max, avg, p95 }, issues: NetworkIssue[] }`
- **Side effects**: opens/closes network connections (diagnostic only)

## Decision Flow

1. **DNS resolution**
   - Resolve: A, AAAA, CNAME records
   - DNSSEC: validate if available
   - Multiple IPs: check all resolved addresses
   - Resolution time: measure DNS lookup latency
   - Cache check: compare resolved IPs against known good values
   - Issues: NXDOMAIN (doesn't exist), SERVFAIL (server error), timeout (unreachable DNS)

2. **TCP reachability**
   - SYN to target:port, wait for SYN-ACK
   - Timeout: 5s default, configurable
   - Firewall detection: RST (rejected) vs no response (dropped/filtered)
   - Port open: SYN-ACK received → connection possible → immediately RST (don't complete handshake)
   - Multiple ports: check common ports (80, 443, 8080, 8443)

3. **TLS health**
   - Handshake: TLS 1.2+ required, TLS 1.3 preferred
   - Certificate: not expired, CN/SAN matches hostname, trusted chain
   - Cipher: check cipher suite strength (no RC4, no export-grade)
   - Certificate transparency: SCT present
   - OCSP stapling: revocation check available
   - Days until expiry: warn at 30 days, alert at 7 days

4. **Latency measurement**
   - TCP handshake time: SYN → SYN-ACK round trip
   - TLS handshake time: full TLS negotiation duration
   - HTTP-level: time to first byte (TTFB) with HEAD request
   - Samples: take 5 measurements, discard highest and lowest, average middle 3
   - Jitter: variation between measurements

5. **Traceroute diagnostics**
   - UDP or ICMP trace to target
   - Hop count: excessive hops (>20) → routing inefficiency
   - Star hops: routers not responding (normal, note not fail)
   - AS path: which autonomous systems does traffic traverse?
   - Bottleneck detection: hop with highest latency increase

## Failure Modes
| Condition | Response |
|---|---|
| DNS resolution fails | Report DNS error, suggest checking hostname, try alternate DNS |
| All TCP ports unreachable | Report connectivity failure, suggest firewall/VPN check |
| TLS certificate expired | Report expiry date, warn about security, suggest renewal |
| Traceroute blocked (firewall) | Report blocked, skip traceroute, use TCP ping as fallback |
| IPv6 not available | Fall back to IPv4, note that IPv6 is unavailable |
