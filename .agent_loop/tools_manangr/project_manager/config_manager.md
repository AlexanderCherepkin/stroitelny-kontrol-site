# Config Manager

## Role
Manages project configuration across all formats — read, write, validate, migrate, and sync configuration files. Single pane of glass for every config file in the project regardless of format.

## Contract
- **Receives**: `{ path: string, action: "read"|"write"|"validate"|"migrate"|"sync"|"diff", key: string, value: any, format: "json"|"yaml"|"toml"|"ini"|"env"|"xml" }`
- **Returns**: `{ config: object, changes: Change[], validation: ValidationResult[], diff: DiffEntry[] }`
- **Side effects**: writes to config files on disk (write/migrate/sync actions)

## Decision Flow

1. **Discover config files**
   - Scan project root and common config locations (`.config/`, `config/`, `src/config/`)
   - Detect format: file extension + content sniffing
   - Classify by purpose: build, runtime, deploy, test, linting, formatting, CI/CD, secrets
   - Build config registry: `{ path, format, schema (if found), last_modified, size }`

2. **Read and merge**
   - Parse file in detected format with schema-aware deserialization
   - Multi-file merge: env-specific overrides (`.env.dev` over `.env.base`)
   - Hierarchical merge: deep-merge nested objects, concat arrays, override scalars
   - Source tracking: each value tagged with origin file path
   - Secret redaction: never return values from `.env`, `.secrets`, vault references

3. **Validate configuration**
   - Schema validation: match against JSON Schema / YAML schema if provided
   - Required keys check: fail if mandatory config is missing
   - Type checking: string where number expected, malformed URLs, invalid enums
   - Cross-file consistency: same key with conflicting values across files
   - Environment completeness: are all `process.env.X` references defined?
   - Security scan: hardcoded secrets, weak defaults, overly permissive settings

4. **Write changes**
   - Preserve format: same indentation, quoting style, comments
   - Atomic write: write to temp file, validate, then rename over target
   - Backup: keep `.bak` of previous version
   - Schema check: refuse to write if new value violates schema

5. **Migrate between formats**
   - JSON → YAML, TOML → JSON, INI → YAML, etc.
   - Preserve: values, structure, comments where format supports them
   - Warn: lossy conversions (comments in JSON, nested objects in INI)
   - Generate migration script for repeatable runs

6. **Sync environments**
   - Compare: local vs staging vs production config
   - Detect drift: keys in one env but not another
   - Generate sync plan with per-key actions (add, update, delete, keep)
   - Secret rotation: detect expired secrets, generate new ones, update references

## Failure Modes
| Condition | Response |
|---|---|
| Malformed config file (parse error) | Report exact line/column of parse error, refuse partial read |
| Format mismatch (extension says YAML, content is JSON) | Auto-detect by content, warn about extension mismatch |
| Write to read-only location | Report permission error, suggest `sudo` or alternate path |
| Schema not found | Validate only structure (valid JSON/YAML), flag missing schema |
| Merge conflict (same key, different types) | Report conflict with sources, require manual resolution |
| Secret detected in non-secret file | Redact from output, flag in security report, suggest `.env` |
