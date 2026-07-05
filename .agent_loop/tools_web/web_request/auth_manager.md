# Auth Manager

## Role
Manages authentication for web requests — token acquisition, refresh, rotation, and injection across all common auth schemes. Single authority for "how do I prove who I am" to any API.

## Contract
- **Receives**: `{ scheme: "bearer"|"basic"|"api_key"|"oauth2"|"digest"|"mtls"|"aws_sigv4", credentials: CredentialConfig, action: "authenticate"|"refresh"|"revoke"|"validate" }`
- **Returns**: `{ headers: object, token_expiry?: ISO8601, scheme: string, warnings: string[] }`
- **Side effects**: may call external token endpoints (OAuth2), may update stored credentials

## Decision Flow

1. **Resolve credentials**
   - Direct: pass credentials inline (basic user:pass, bearer token string, API key value)
   - Environment: read from `API_KEY`, `CLIENT_SECRET`, `OAUTH_TOKEN`
   - Secrets manager: fetch from vault/AWS Secrets Manager
   - File: read from `.env`, `~/.netrc`, service-account JSON
   - Priority: explicit > environment > secrets manager > file

2. **Authenticate by scheme**
   - `bearer`: `Authorization: Bearer <token>` — validate JWT expiry, refresh if needed
   - `basic`: `Authorization: Basic <base64(user:pass)>` — warn about plaintext over HTTP
   - `api_key`: inject per API convention (header `X-API-Key: <key>`, query param, or custom header)
   - `oauth2`: client_credentials flow → POST to token endpoint → cache access_token → auto-refresh
   - `digest`: handle server nonce challenge → compute HA1/MD5 hash → send Authorization header
   - `mtls`: load client cert + key, attach to TLS context
   - `aws_sigv4`: sign request with AWS credentials → `Authorization: AWS4-HMAC-SHA256 ...`

3. **Token lifecycle (OAuth2)**
   - Store: access_token, refresh_token, expires_at, scope
   - Preemptive refresh: if expires in < 60s, refresh before sending request
   - Refresh flow: POST refresh_token → new access_token + refresh_token → update store
   - Refresh failure: clear stored tokens, fall back to re-authentication
   - Token revocation: POST to revoke endpoint on logout or credential rotation
   - Token validation: decode JWT, check exp, verify signature against JWKS if available

4. **Credential rotation**
   - Scheduled: rotate API keys every 90 days
   - Event-driven: rotate on security incident or permission change
   - Overlap: generate new credential → deploy → wait → revoke old
   - Rollback: keep old credential active during transition window

5. **Security checks**
   - Never log credentials or Authorization headers
   - Redact from error messages and stack traces
   - HTTPS required for bearer/basic (warn on HTTP)
   - Basic auth: reject credentials containing newlines (injection)
   - Token scope: verify token has required scopes before request
   - Expiry buffer: treat token as expired 30s before actual expiry (clock skew)

## Failure Modes
| Condition | Response |
|---|---|
| Token expired, refresh fails | Clear stored token, report re-authentication required |
| OAuth2 token endpoint unreachable | Use cached token if still valid, fail if expired |
| Invalid credentials (401 response) | Do not retry with same credentials, report auth failure |
| mTLS cert expired or invalid | Report cert details, suggest renewal path |
| API key in plaintext over HTTP | Warn strongly, suggest HTTPS or key rotation |
