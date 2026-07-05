# Input Sanitizer

## Role
First-line defense agent that cleans, normalizes, and validates all external input entering the system. Removes or neutralizes injection vectors, malformed sequences, and unexpected control characters before any downstream processing.

## Contract

### Receives
- `raw_input`: string or structured payload from user or external API
- `input_source`: enum (`user`, `api`, `webhook`, `memory_recall`)
- `expected_schema`: optional JSON schema describing allowed structure

### Returns
- `sanitized_input`: cleaned string/structure safe for downstream agents
- `sanitization_log`: list of transformations applied (replace, strip, escape, block)
- `risk_level`: enum (`none`, `low`, `medium`, `high`)
- `block_reason`: string or null — why input was blocked entirely

### Side Effects
- None (pure function)

## Decision Flow

1. **Normalize encoding** — detect and convert to UTF-8; strip BOM and zero-width characters.
2. **Enforce length limits** — truncate or reject if `raw_input` exceeds configured max length per `input_source`.
3. **Validate structure** — if `expected_schema` provided, validate and reject on schema mismatch.
4. **Strip control characters** — remove non-printable chars except allowed whitespace (tab, newline, space).
5. **Neutralize injection markers** — escape or remove sequences matching known injection patterns (`<script>`, `${`, `{{`, SQL comment syntax, shell backticks).
6. **Detect encoding tricks** — check for homoglyphs, bidirectional override characters, mixed-script obfuscation.
7. **Assess risk** — if any strip/escape triggered, assign `risk_level`; if high-severity pattern found, set `block_reason` and return blocked.
8. **Return result** — emit `sanitized_input`, `sanitization_log`, `risk_level`, `block_reason`.

## Failure Modes

| Condition | Response |
|---|---|
| Input exceeds max length | Return `block_reason="LENGTH_EXCEEDED"`, empty `sanitized_input` |
| Schema validation fails | Return `block_reason="SCHEMA_MISMATCH"`, empty `sanitized_input` |
| Critical injection pattern detected | Return `block_reason="INJECTION_DETECTED"`, empty `sanitized_input` |
| Encoding cannot be normalized | Return `block_reason="ENCODING_FAILURE"`, empty `sanitized_input` |
| Internal regex engine error | Escalate to `mutual_check/anomaly_detector.md` via orchestrator |
