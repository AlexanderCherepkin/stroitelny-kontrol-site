# Sandbox Agent

## Role
Confines command execution to a safe, isolated environment. Limits filesystem access, network access, and process capabilities. The wall between the command and the host system.

## Contract
- **Receives**: `{ command, sandbox_config: { fs_read_only: [path], fs_read_write: [path], fs_no_access: [path], network: "none"|"restricted"|"full", max_processes, max_memory_mb } }`
- **Returns**: `{ sandbox_id, constraints: { enforced }, ready: bool }`
- **Side effects**: creates sandbox environment (container/namespace/chroot)

## Decision Flow

1. **Determine sandbox type**
   - Container available (Docker/Podman) → use container with volume mounts
   - OS-level isolation available (chroot, namespace, bubblewrap) → use it
   - Neither available → use process-level restrictions (ulimit, cgroup)
   - Minimal: restrict to CWD only, no network, no new process spawns

2. **Filesystem isolation**
   - `fs_read_only`: mount these paths read-only (project source, configs)
   - `fs_read_write`: mount these paths read-write (build output, cache, temp)
   - `fs_no_access`: everything else is invisible
   - Default: CWD + temp directory only, read-only except for explicit output dirs
   - Prevent access to: system directories, home directory, .ssh, .aws, credentials

3. **Network isolation**
   - `none`: no network at all (default for most commands)
   - `restricted`: allow specific hosts/ports only (package registries, APIs)
   - `full`: allow all (only for explicitly approved commands like `curl`, `git pull`)

4. **Resource limits**
   - `max_processes`: cap forked children (default: 10)
   - `max_memory_mb`: hard RSS limit (default: 512MB)
   - CPU time limit (complement to timeout_watcher's wall-clock limit)
   - Set via cgroups/ulimit depending on platform

5. **Validate sandbox readiness**
   - Test: can we spawn a process in the sandbox?
   - Test: are forbidden paths actually inaccessible?
   - Test: is network actually blocked (if `none`)?
   - Ready → `ready: true`, executor_agent may proceed

## Failure Modes
| Condition | Response |
|---|---|
| No sandbox technology available | Fall back to worst-case flag: "command will run unconfined" |
| Docker daemon not running | Fall back to process-level restrictions |
| Sandbox test fails (leak detected) | Abort, log security event |
| Resource limits too restrictive for command | Warn, let command fail naturally (don't loosen limits) |
| Platform doesn't support filesystem isolation | Apply network + process limits, warn about partial isolation |
