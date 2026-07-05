# Output Collector

## Role
Captures stdout and stderr from the child process. Streams output efficiently, enforces size limits, and preserves structure (lines, ANSI codes, encoding).

## Contract
- **Receives**: `{ stdout_stream, stderr_stream, options: { max_stdout_bytes, max_stderr_bytes, preserve_ansi: bool, encoding } }`
- **Returns**: `{ stdout: string, stderr: string, truncated: { stdout: bool, stderr: bool }, byte_counts: { stdout, stderr }, line_counts: { stdout, stderr } }`
- **Side effects**: none (reads from pipes only)

## Decision Flow

1. **Read streams concurrently**
   - stdout and stderr read in separate buffers (non-blocking I/O)
   - Read in chunks (64KB default) to avoid memory pressure
   - Decode bytes to string using detected/configured encoding

2. **Enforce size limits**
   - `max_stdout_bytes` (default: 1MB), `max_stderr_bytes` (default: 256KB)
   - When limit reached → stop reading, set `truncated: true`, discard remainder
   - If truncated: keep first 90% of allowed bytes, add `...[truncated]` with last 10%
   - Never silently truncate — always flag

3. **Structure preservation**
   - Preserve line boundaries (don't split mid-line, even at chunk boundaries)
   - If `preserve_ansi: true` → keep ANSI escape codes (colors, progress bars)
   - If `preserve_ansi: false` → strip ANSI codes (clean text for LLM consumption)

4. **Encoding handling**
   - Default: UTF-8 for both streams
   - If invalid UTF-8 detected → fall back to Latin-1, flag encoding issue
   - Binary output detection: if >30% non-printable bytes → flag as likely binary

5. **Aggregate and return**
   - Combine timestamped chunks in order
   - Report line counts (useful for sizing command output)
   - If both stdout and stderr are empty → flag (command may have failed silently)

## Failure Modes
| Condition | Response |
|---|---|
| Output exceeds limit and is truncated | Flag `truncated: true`, report original byte count estimate |
| Mixed encoding in output | Decode with best effort, flag problematic regions |
| Binary output detected | Return hexdump-style preview + `"[binary output: N bytes]"` |
| Stream read error (pipe broken) | Return partial output + error metadata |
| stdout and stderr both empty | Return empty strings + note (may indicate silent failure) |
