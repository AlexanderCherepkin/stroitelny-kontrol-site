# Session Manager

## Role
Manages the lifecycle of an interactive terminal session. Creates, authenticates, monitors, and tears down connections. One session per terminal — stateful, long-lived, unlike one-shot commands.

## Contract
- **Receives**: `{ target: { host, port, protocol: "ssh"|"docker"|"local"|"websocket" }, credentials: { type: "key"|"password"|"token" }, session_config: { idle_timeout_ms, max_duration_ms } }`
- **Returns**: `{ session_id, status: "connected"|"connecting"|"disconnected", capabilities: { pty, env_vars, shell_type } }`
- **Side effects**: creates connection, spawns shell process (if local), opens network socket (if remote)

## Decision Flow

1. **Create session**
   - `local`: spawn a shell process (bash, zsh, cmd, powershell) with PTY
   - `ssh`: open SSH connection, authenticate, allocate PTY
   - `docker`: `docker exec -it <container> <shell>`, attach stdin/stdout/stderr
   - `websocket`: connect to remote terminal server, upgrade to WS
   - Generate unique `session_id`, record start time

2. **Authenticate**
   - Key-based: use provided private key path or agent
   - Password: use provided password (never log it)
   - Token: pass as bearer/auth header
   - Local: inherit current user permissions
   - Auth failure → destroy session, return error

3. **Configure PTY**
   - Set terminal type (xterm-256color, vt100, dumb)
   - Set window size (rows × columns) — update on resize
   - Set environment variables in the session
   - Detect shell type and version

4. **Monitor health**
   - Periodic heartbeat: send echo command, check response
   - Idle timeout: if no I/O for `idle_timeout_ms` → auto-disconnect
   - Max duration: hard cap at `max_duration_ms` → force disconnect
   - Detect dead sessions: process exited, connection lost, PTY closed

5. **Teardown**
   - Send exit command or close PTY gracefully
   - Wait for process/connection to close (graceful period: 2s)
   - Force kill if still alive
   - Release all resources: FDs, sockets, child processes

## Failure Modes
| Condition | Response |
|---|---|
| SSH connection refused | Retry once, then report: "host unreachable or SSH not running" |
| Authentication failed | Report: "auth failed" (never reveal which part: user vs key vs password) |
| Shell type unknown | Default to sh, flag limited functionality |
| Idle timeout | Disconnect with "session idle for {N}ms", preserve session state for resume |
| Session killed externally | Detect, update status to "disconnected", report who/what killed it |
