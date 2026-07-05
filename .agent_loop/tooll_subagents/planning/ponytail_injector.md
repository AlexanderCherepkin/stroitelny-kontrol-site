# Ponytail Injector

## Role
Prepend the Ponytail protocol to the system prompt of any agent about to generate or refactor code. Acts as a lightweight policy gate that activates laziness rules without changing the underlying agent contract.

## Contract

### Receives
- `base_system_prompt`: string — original system prompt of the target agent.
- `task_type`: string | None — request classification from `user/request.md` (e.g., `code_change`, `refactor`, `fix`, `design_project`, `general`).
- `ponytail_mode`: string | None — explicit override (`lite`, `full`, `ultra`, `off`). Falls back to `PONYTAIL_DEFAULT_MODE` env, then to `full`.
- `request_context`: optional string — short user request summary used to detect non-coding prose.

### Returns
- `optimized_system_prompt`: string — base prompt with Ponytail rules prepended, or unchanged if disabled/non-coding.
- `mode_applied`: string — effective mode (`lite`, `full`, `ultra`, `off`).
- `guardrails`: list[string] — active safety guardrails from the protocol (validation, error handling, a11y, tests, DB integrity).
- `injected`: boolean — true if the Ponytail block was prepended.

### Side effects
- Logs mode selection and injection decision to `audit_logger.md`.

## Decision Flow

1. **Resolve effective mode** — use `ponytail_mode` override if valid; otherwise read `PONYTAIL_DEFAULT_MODE` env; default to `full`.
2. **Validate mode** — if the resolved mode is not in `{lite, full, ultra, off}`, fall back to `full` and log a warning to `audit_logger.md`.
3. **Classify task** — if `task_type` is non-coding (e.g., `general`, `question`, `summary`, `translation`, `prose`, `recipe`, `chat`), force `mode_applied=off` for this call.
4. **Short-circuit if off** — if effective mode is `off`, return `base_system_prompt` unchanged with `injected=false`.
5. **Build Ponytail block** — concatenate the core protocol prompt and the mode-specific instruction.
6. **Prepend to base prompt** — return the Ponytail block followed by the original system prompt; set `injected=true`.
7. **Return metadata** — emit `optimized_system_prompt`, `mode_applied`, `guardrails`, and `injected`.

## Failure Modes

| Condition | Response |
|---|---|
| Unknown `ponytail_mode` override | Fall back to env/default `full`; log warning |
| `base_system_prompt` is empty or missing | Return the Ponytail block alone as the system prompt |
| Non-coding task with active coding mode | Force `mode_applied=off` for this call; log reason |
| Env variable contains invalid mode | Treat as `full`; log malformed env value |
| `task_type` is ambiguous | Default to applying Ponytail (coding assumption); log ambiguity |
