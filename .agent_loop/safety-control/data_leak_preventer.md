# Data Leak Preventer

## Role
Privacy and compliance gate that scans outgoing content for sensitive data leakage. Prevents accidental exposure of credentials, personal information, proprietary code, and internal system details in agent outputs or tool logs.

## Contract

### Receives
- `output_content`: string or binary payload intended for external transmission
- `classification_level`: enum (`public`, `internal`, `confidential`, `restricted`)
- `recipient_scope`: enum (`user`, `log`, `third_party_api`, `public_channel`)
- `detection_rules`: optional custom regex or entity list

### Returns
- `leak_detected`: boolean
- `leaked_entities`: list of detected sensitive fragments with type and position
- `redacted_output`: sanitized copy of `output_content` with sensitive parts replaced by `[REDACTED:type]`
- `severity`: enum (`none`, `low`, `medium`, `high`, `critical`)
- `action`: enum (`pass`, `redact`, `block`)

### Side Effects
- Writes detection event to security audit log
- Triggers alert if `severity=critical`

## Decision Flow

1. **Select detector set** — based on `classification_level` and `recipient_scope`, load appropriate rule set (PII, credentials, IP addresses, internal hostnames, proprietary markers). For browser-generated content (`screenshot_path`, `cookies`, `localStorage`, `network_intercept`), add browser-specific rules: auth tokens in URLs, session cookies, cached credentials.
2. **Entity extraction** — scan for known patterns (email, phone, SSN, credit card, API keys, tokens, passwords, database connection strings). Also detect `Set-Cookie`, `Authorization`, and browser-storage key/value pairs.
4. **Contextual scoring** — reduce false positives by checking surrounding tokens (`key=`, `token=`, `password:`).
5. **Aggregate severity** — `critical` for plaintext credentials to `public_channel`; `high` for PII; `medium` for internal hostnames; `low` for vague mentions.
6. **Determine action** — `block` if `severity=critical`; `redact` if `severity=high` or `medium` and `recipient_scope=third_party_api`; `pass` if `severity=low` or none.
7. **Produce redacted copy** — if `redact`, replace each leaked entity with `[REDACTED:type]` preserving length hint.
8. **Return and log** — emit result, write audit entry.

## Failure Modes

| Condition | Response |
|---|---|
| Detection ruleset missing | `action=block`, `severity=critical`, `leak_detected=true` (fail closed) |
| Output exceeds scan buffer | Stream-scan in chunks; if boundary split obscures entity, `action=escalate` to `mutual_check/result_validator.md` |
| Redaction corrupts structured format (JSON) | Switch to token-preserving mask (`"key": "[REDACTED]"`) |
| Entropy classifier false-negative on short secret | Compensate by checking against known-prefix database (AWS AKIA, GitHub ghp_) |
| Browser screenshot or network traffic contains unredacted secrets | `action=block`, `severity=critical`; route to `tools_browser/headless_automation/error_handler.md` for cleanup |
| Alert channel failure | Buffer alert in local queue; retry 3× before escalating to `control/human_oversight.md` |
