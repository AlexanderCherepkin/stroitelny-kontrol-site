# Response Parser

## Role
Parses HTTP responses — status codes, headers, body deserialization, pagination detection, and structured error extraction. Translates raw HTTP responses into typed, actionable results.

## Contract
- **Receives**: `{ response: { status, headers, body }, expect: "json"|"xml"|"html"|"text"|"binary"|"auto", schema?: JSONSchema }`
- **Returns**: `{ parsed: any, status: StatusInfo, pagination?: Pagination, warnings: string[], headers: ParsedHeaders }`
- **Side effects**: none (pure transformation)

## Decision Flow

1. **Interpret status code**
   - 1xx Informational: handle 100 Continue, 101 Switching Protocols
   - 2xx Success: 200 OK, 201 Created, 202 Accepted (async), 204 No Content, 206 Partial Content
   - 3xx Redirect: extract Location header, follow or report
   - 4xx Client error: 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 409 Conflict, 422 Unprocessable, 429 Rate Limited
   - 5xx Server error: 500 Internal, 502 Bad Gateway, 503 Unavailable, 504 Gateway Timeout
   - Classify: success (2xx), client_error (4xx), server_error (5xx), redirect (3xx)

2. **Parse headers of interest**
   - `Content-Type`: media type + charset (e.g., `application/json; charset=utf-8`)
   - `Content-Length`: body size in bytes
   - `Content-Encoding`: gzip, deflate, br → decompress body
   - `ETag`: entity tag for conditional requests
   - `Last-Modified`: timestamp for cache validation
   - `Cache-Control`: max-age, no-cache, no-store, private, public
   - `Link`: parse for pagination (rel="next", rel="prev", rel="last", rel="first")
   - `Set-Cookie`: parse cookie directives (HttpOnly, Secure, SameSite)

3. **Deserialize body**
   - `auto` detect: check Content-Type header, fall back to content sniffing
   - JSON: `JSON.parse()`, validate against schema if provided
   - XML: parse DOM, convert to JSON-like structure, handle namespaces
   - HTML: parse DOM tree, extract text and metadata
   - Text: return as string, detect encoding from charset
   - Binary: return as Buffer/Uint8Array, detect MIME type from magic bytes
   - NDJSON/JSON Lines: split by newline, parse each line

4. **Schema validation**
   - JSON Schema: validate parsed body against provided schema
   - Required fields: flag missing, continue parsing rest
   - Type mismatches: flag, attempt coercion (string "123" → int 123)
   - Unknown fields: include, warn (API may have added new fields)
   - Detailed report: `[ { path: "$.user.email", error: "expected string, got null" } ]`

5. **Pagination detection**
   - Link header (RFC 5988): parse rel="next"/"prev"/"first"/"last" URLs
   - Offset-based: `?offset=20&limit=10` pattern
   - Cursor-based: `?after=<cursor>` or `?page_token=<token>`
   - Page-based: `?page=2&per_page=20`
   - Total count: `X-Total-Count`, `X-Total`, or `total` in response body
   - Next page URL ready for subsequent request

6. **Error body extraction**
   - Standard formats: RFC 7807 Problem Details (`type`, `title`, `detail`, `instance`)
   - JSON API errors: `{ errors: [{ code, detail, source: { pointer } }] }`
   - GraphQL errors: `{ errors: [{ message, locations, path, extensions }] }`
   - Generic: extract `error`, `message`, `errors`, `detail`, `description`
   - Fallback: first 500 chars of body as error string

## Failure Modes
| Condition | Response |
|---|---|
| Content-Type says JSON but body is not | Flag content-type mismatch, try parsing as declared type, fall back to text |
| Body decompression fails | Return compressed body as-is, flag decompression error |
| Schema validation errors | Return partial data + error list, do not throw away valid data |
| Unknown charset | Default to UTF-8, warn about encoding assumption |
| Response is HTML with error message (e.g., cloudflare error page) | Extract text from HTML, classify as infrastructure error |
