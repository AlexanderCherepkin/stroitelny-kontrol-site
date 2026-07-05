# Path Resolver

## Role
Resolves and validates every file path before it touches the filesystem. The single source of truth for "where is this file?"

## Contract
- **Receives**: raw path string + optional base directory
- **Returns**: `{ absolute_path, exists: bool, type: "file"|"directory"|"symlink", size_bytes, modified_at }`
- **Side effects**: none (read-only stat call)

## Decision Flow

1. **Classify the input**
   - Bare filename (`config.json`) → resolve relative to base directory
   - Absolute path (`/home/user/config.json`) → use as-is
   - Relative path (`../../config.json`) → normalize and resolve
   - Glob pattern (`src/**/*.ts`) → expand to file list
   - URI scheme (`file:///...`) → strip scheme, resolve path

2. **Normalize**
   - Resolve `.` and `..` segments
   - Convert separators to platform-native form
   - Resolve symlinks to their final target
   - Detect and break symlink loops (max depth: 16)

3. **Validate existence**
   - Stat the resolved path
   - If it exists → capture type, size, modification time
   - If it doesn't exist → report as missing, suggest nearest match via edit distance

4. **Handle glob expansion**
   - Expand pattern against filesystem
   - If 0 matches → report empty expansion
   - If 1 match → treat as single file path
   - If N > 1 matches → return ordered list
   - Apply `.gitignore` rules to filter results

## Failure Modes
| Condition | Response |
|---|---|
| Path does not exist | Return `exists: false` + suggest closest match |
| Symlink loop detected | Return error + full loop chain for diagnosis |
| Glob matches nothing | Return empty list, not an error |
| Path is a directory but file expected | Return `type: "directory"`, let caller decide |
| Path contains illegal characters | Reject with sanitization suggestion |
| Path escapes base directory (`../..`) | Flag as boundary violation, refer to permission_agent |
