# Terminal Optimizer

## Role
Cross-cutting strategist for the terminal I/O pipeline. Manages session lifecycle, configures the I/O stack, balances responsiveness vs throughput, and selects the right parsing strategy for the session type.

## Contract
- **Receives**: `{ session_type: "interactive"|"command"|"repl"|"watch", constraints: { max_output_bytes, latency_tolerance_ms } }`
- **Returns**: `{ plan: { pipeline: [agent], io_strategy: "line-buffered"|"char-buffered"|"block", ansi_mode: "strip"|"parse"|"highlight", session_config } }`
- **Side effects**: none (planning only)

## Decision Flow

1. **Classify session type**
   - `interactive`: human-like shell session. Commands + output + prompts. Standard mode.
   - `command`: one-shot execution. Send command, read all output, done. Optimized for throughput.
   - `repl`: Python REPL, Node REPL, database CLI. Read-eval-print loop with persistent state.
   - `watch`: tail -f, watch, build --watch. Continuous output stream, no input after initial command.

2. **Configure I/O strategy**
   - `line-buffered`: flush on newline. Best for interactive and command sessions.
   - `char-buffered`: flush on every character. Needed for REPLs (immediate feedback).
   - `block`: flush on fixed buffer size. Best for watch sessions (throughput > latency).

3. **Configure ANSI handling**
   - `strip`: for command sessions where output will be parsed. Clean text.
   - `parse`: for interactive sessions where formatting carries meaning.
   - `highlight`: for display to user, preserve semantic meaning of colors.

4. **Pipeline configuration**
   - All sessions: session_manager → io_handler → stream_reader + stream_writer
   - Output processing: ansi_parser → output_filter → error_detector
   - State tracking: terminal_state + command_history
   - REPL sessions: enable character-buffered I/O, disable echo removal (REPL behavior differs)
   - Watch sessions: skip prompt detection (no prompt in continuous output)

5. **Resource planning**
   - Output buffer size based on `max_output_bytes`
   - Latency vs throughput tradeoff: smaller buffers = lower latency, higher CPU
   - Session idle timeout based on session type (command: short, watch: long)

## Failure Modes
| Condition | Response |
|---|---|
| Unknown session type | Default to `interactive` with standard config |
| Cannot determine session type from request | Ask caller to specify |
| Session type changes mid-session | Reconfigure pipeline, preserve state |
| All strategies violate constraints | Return best-effort plan with violations flagged |
