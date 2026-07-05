# Stream Reader

## Role
Reads raw bytes from terminal stdout/stderr and converts them into structured events. The lowest-level I/O agent — bytes in, parsed events out.

## Contract
- **Receives**: `{ session_id, stream: "stdout"|"stderr"|"both", options: { buffer_size, read_timeout_ms } }`
- **Returns**: `{ events: [{ type: "text"|"ansi_sequence"|"bell"|"control_char", data, timestamp }], bytes_read }`
- **Side effects**: reads from PTY/socket (non-blocking)

## Decision Flow

1. **Read available data**
   - Non-blocking read from PTY or socket
   - `read_timeout_ms`: max time to wait for data (default: 100ms)
   - If no data → return empty events (not an error)
   - `buffer_size`: max bytes per read (default: 64KB)

2. **Split into events**
   - Plain text: printable characters, newlines, tabs → `type: "text"`
   - ANSI escape sequence: `\x1b[...` → `type: "ansi_sequence"`, pass raw bytes + parsed to ansi_parser
   - Control characters: `\x03` (Ctrl+C), `\x04` (Ctrl+D), `\x07` (BEL/bell), `\x08` (BS), `\x7f` (DEL)
   - Null bytes → ignore, log warning
   - Incomplete UTF-8 sequence at buffer end → hold in partial buffer, complete on next read

3. **Line buffering**
   - Accumulate text events until newline or timeout
   - Flush line: newline received, or 500ms since last byte, or prompt detected
   - Each flushed line is one coherent chunk for downstream analysis

4. **Detect special sequences**
   - Prompt markers: `$ `, `# `, `> ` at line end after inactivity
   - Command echo: terminal echoing back our input
   - Bell: `\x07` → application alert
   - Clear screen: `\x1b[2J` → terminal reset

## Failure Modes
| Condition | Response |
|---|---|
| Read timeout (no data) | Return empty events — normal idle state |
| PTY closed unexpectedly | Return remaining buffered data + `stream_closed` event |
| Invalid UTF-8 sequence | Replace with U+FFFD, flag encoding issue |
| Buffer too small for ANSI sequence | Extend buffer, re-read, warn once |
| Binary data in stream | Hex-encode, flag, don't try to interpret as text |
