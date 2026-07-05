# Stream Writer

## Role
Writes agent commands and input to the terminal's stdin. Handles encoding, batching, and special key sequences. The agent's voice into the terminal.

## Contract
- **Receives**: `{ session_id, input: string|Buffer, options: { encoding, simulate_typing: bool, typing_delay_ms } }`
- **Returns**: `{ bytes_written, acknowledged: bool }`
- **Side effects**: writes to PTY/socket stdin

## Decision Flow

1. **Encode input**
   - Convert string to bytes using session encoding (default: UTF-8)
   - CR/LF handling: `\n` → `\r\n` for raw PTY, `\n` for cooked mode
   - Special characters: tab (`\t`), escape (`\x1b`)
   - Binary input: pass raw bytes (hex-encoded strings → bytes)

2. **Simulate typing (optional, for interactive commands)**
   - `simulate_typing: true` → send character by character with `typing_delay_ms` between
   - Use for: interactive editors (vim, nano), password prompts, interactive CLI tools
   - `simulate_typing: false` → send entire command at once (paste mode)
   - Human-like: random jitter on delay (±20%) to avoid detection as bot

3. **Handle special keys**
   - Ctrl+C (`\x03`) → interrupt current process
   - Ctrl+D (`\x04`) → EOF (exit shell if at empty prompt)
   - Ctrl+Z (`\x1a`) → suspend process (SIGTSTP)
   - Arrow keys → ANSI escape sequences (`\x1b[A` up, `\x1b[B` down, etc.)
   - Tab (`\x09`) → autocomplete trigger
   - Escape (`\x1b`) → meta key, mode switch

4. **Flow control awareness**
   - Check io_handler flow state before writing
   - `ready` → write immediately
   - `busy` → queue (don't interleave with running command output)
   - `blocked` → this input is the response to an interactive prompt, write immediately
   - After write: signal command_sent to terminal_state and command_history

## Failure Modes
| Condition | Response |
|---|---|
| Stdin closed (process exited) | Report, do not attempt write |
| Write partially successful (wrote N of M bytes) | Retry remaining bytes, then flag |
| Terminal in busy state | Queue, wait for ready, timeout after 30s |
| Input too large (>1MB single write) | Reject, suggest splitting into chunks |
| Encoding fails (invalid chars for target encoding) | Fall back to ASCII with replacements, flag |
