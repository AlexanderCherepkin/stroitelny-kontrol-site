# Request Builder

## Role
Constructs HTTP requests — method, URL, headers, query params, body, multipart form data, with content negotiation and dialect-aware defaults. The single entry point for building any outbound HTTP request.

## Contract
- **Receives**: `{ method: "GET"|"POST"|"PUT"|"PATCH"|"DELETE"|"HEAD"|"OPTIONS", url: string, headers: object, query: object, body: any, options: { timeout_ms, follow_redirects, max_redirects, compress } }`
- **Returns**: `{ request: { url, method, headers, body, options }, fingerprint: string }`
- **Side effects**: none (pure construction)

## Decision Flow

1. **Parse and validate URL**
   - Parse: scheme (https enforced, http warn), host, port, path, query, fragment
   - Validate: scheme must be http/https, host must be resolvable, path must be valid
   - Encode: path segments (spaces → %20), query params (?, &, =)
   - Default ports: https → 443, http → 80 unless explicitly set
   - Remove fragment before sending (server never sees it)

2. **Build headers**
   - Defaults: `Accept: application/json`, `Accept-Encoding: gzip, deflate, br`, `User-Agent: AgenticLoop/1.0`
   - Content-Type auto-detect: JSON body → `application/json`, FormData → `multipart/form-data`, URL-encoded → `application/x-www-form-urlencoded`, text → `text/plain`
   - Content-Length: compute from body, set automatically
   - Host: derived from URL
   - Authorization: delegate to auth_manager
   - Custom: user-provided headers override defaults
   - Redact: never log Authorization, Cookie, Set-Cookie headers

3. **Build query string**
   - Serialize: object → `key=value&key2=value2`
   - Array format: `key[]=a&key[]=b` (default) or `key=a&key=b` (repeat) or `key=a,b` (comma)
   - Null values: omit (default) or `key=` (empty)
   - Booleans: `true`/`false` strings
   - Nested objects: `parent[child]=value` bracket notation
   - Encoding: percent-encode special characters

4. **Build request body**
   - JSON: `JSON.stringify()` with content-type header
   - Form URL-encoded: serialize as query string in body
   - Multipart: boundary generation, part headers (Content-Disposition, Content-Type per part)
   - Binary: pass through as buffer with appropriate content-type
   - Empty body: GET/HEAD/DELETE typically have no body
   - Size check: warn if body > 10MB, reject if > 100MB (configurable)

5. **Generate request fingerprint**
   - Normalize: method + host + path (no query params, no headers)
   - Hash for deduplication and caching keys
   - Include: major API version from URL path for versioned APIs

## Failure Modes
| Condition | Response |
|---|---|
| Invalid URL (malformed) | Reject, point to syntax error in URL |
| HTTP scheme requested | Warn about lack of encryption, allow if explicitly permitted |
| Body too large (>100MB) | Reject, suggest streaming upload or chunking |
| Unsupported content type | Default to application/octet-stream, warn |
| Query param object too deep (>5 levels) | Flatten with bracket notation, warn about API compatibility |
