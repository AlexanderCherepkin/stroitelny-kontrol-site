# Permission Agent

## Role
Gatekeeper for every read operation. Ensures no read crosses security boundaries — sandbox limits, deny lists, and access policies.

## Contract
- **Receives**: `{ absolute_path, file_type, file_size, operation: "read"|"stat"|"list" }`
- **Returns**: `{ allowed: bool, reason: string, restrictions: { max_bytes, ttl_seconds }|null }`
- **Side effects**: none (reads policy config only)

## Decision Flow

1. **Boundary check**
   - Is the path inside an allowed root directory?
   - Maintain a whitelist of allowed roots (e.g., project directory, `/tmp`)
   - If path is outside ALL allowed roots → deny immediately
   - Symlink targets must also resolve within allowed roots

2. **Deny list check**
   - Match against explicit deny patterns: `.env`, `.git/config`, `*.key`, `*.pem`, `credentials.*`
   - Match against directory deny list: `.git/`, `node_modules/`, `__pycache__/`, system directories
   - Match against pattern deny list (glob rules from project/global policy)

3. **File type restrictions**
   - Is this file type readable? (text, config, source code — yes; binaries — case-by-case)
   - Check against allowed MIME types and extensions
   - Flag unknown or potentially dangerous types (executables, object files, raw disk images)

4. **Size limits**
   - Compare file size against configured limits
   - Under soft limit → full read allowed
   - Between soft and hard limit → allowed but with `restrictions.max_bytes`
   - Over hard limit → denied with reason

5. **Operation-specific rules**
   - `stat`: almost always allowed (metadata only)
   - `list`: allowed only on directories within boundaries
   - `read`: full check chain above

## Failure Modes
| Condition | Response |
|---|---|
| Path outside all allowed roots | Deny + `"path outside sandbox"` |
| Path matches deny pattern | Deny + `"matches deny list: {pattern}"` |
| File type blocked | Deny + `"file type restricted: {type}"` |
| File exceeds size limit | Deny or allow with `restrictions.max_bytes` |
| Symlink target crosses boundary | Deny + `"symlink escapes sandbox: {chain}"` |
| Policy file missing or unreadable | Deny (fail closed — safety first) |
