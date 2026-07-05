# IO Handler

## Role
Coordinates bidirectional I/O between the agent and the terminal session. The multiplexer — routes input from agent to terminal, output from terminal to agent, and manages flow control.

## Contract
- **Receives**: `{ session_id, direction: "send"|"receive"|"both" }`
- **Returns**: `{ sent: [{ data, timestamp }], received: [{ data, timestamp, stream: "stdout"|"stderr" }], flow_state: "ready"|"busy"|"blocked" }`
- **Side effects**: writes to stdin, reads from stdout/stderr

## Decision Flow

1. **Send (agent → terminal)**
   - Queue input for writing to terminal stdin
   - If terminal is busy (command running) → queue, don't interleave
   - If terminal is ready → write immediately
   - Handle special keys: Ctrl+C (SIGINT), Ctrl+D (EOF), Ctrl+Z (SIGTSTP), arrows, tabs
   - Batch rapid inputs into single write (reduce syscalls)

2. **Receive (terminal → agent)**
   - Read stdout and stderr streams concurrently
   - Non-blocking: read available bytes, don't wait
   - Buffer partial output (line not complete yet)
   - Flush buffer on: newline, prompt detection, timeout (500ms no new data)
   - Route stderr to error_detector for analysis

3. **Flow control**
   - `ready`: terminal prompt detected, shell idle, can send next command
   - `busy`: command running, output streaming, wait for prompt
   - `blocked`: terminal waiting for input (interactive prompt, password, confirmation)
   - Agent must not send commands in `busy` state (interleave risk)

4. **Interactive prompt handling**
   - Detect: "Are you sure? [y/N]", "Password:", "Enter value:"
   - Route to agent for decision (auto-answer or escalate)
   - Timeout on interactive prompt: 30s → auto-answer "n" or Ctrl+C

## Failure Modes
| Condition | Response |
|---|---|
| Stdin pipe broken (process exited) | Close write side, signal session_manager |
| Stdout pipe closed (EOF) | Finish reading remaining data, update terminal_state |
| Output buffer overflow (>10MB unread) | Flush, flag data loss, apply backpressure |
| Terminal in busy state, agent tries to send | Queue command, warn about interleave risk |
| Interactive prompt detection false positive | Send newline, check if prompt reappears |
