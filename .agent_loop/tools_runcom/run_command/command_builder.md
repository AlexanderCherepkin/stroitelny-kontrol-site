# Command Builder

## Role
Constructs and validates shell commands before execution. Transforms intent ("run tests", "install deps") into safe, well-formed command strings. The first line of defense against injection and malformed commands.

## Contract
- **Receives**: `{ intent: string, context: { shell, cwd, platform }, safety: { allowed_commands, blocked_patterns } }`
- **Returns**: `{ command: string, escaped: bool, warnings: [string], estimated_runtime_ms }`
- **Side effects**: none (pure construction)

## Decision Flow

1. **Parse intent**
   - Literal command provided (`"npm test"`) → validate, don't modify
   - Natural language intent (`"run all tests in the auth module"`) → translate to concrete command
   - Ambiguous intent → request clarification before building

2. **Command construction**
   - Select appropriate shell for the platform (`cmd.exe`, `powershell`, `bash`, `sh`)
   - Build argument list with proper escaping for the target shell
   - Chain multiple commands safely: `&&` (sequential), `|` (pipe), `;` (unconditional)

3. **Injection prevention**
   - Escape all user-provided arguments (shell-specific escaping rules)
   - Reject patterns: backticks in unquoted context, `$(...)`, `eval`, `; rm`, `| sh`
   - Whitelist approach: command must match `allowed_commands` list or be explicitly approved
   - Block commands matching `blocked_patterns` (e.g., `rm -rf /`, `chmod 777`, `curl | bash`)

4. **Estimate runtime**
   - Fast: `ls`, `cat`, `echo`, `git status` (<1s)
   - Medium: `npm install`, `pip install`, `git clone` (10-60s)
   - Slow: `npm test`, `cargo build`, `docker build` (1-10min)
   - Unknown: flag with max timeout, let timeout_watcher enforce

5. **Return**
   - Fully formed, escaped command string
   - List of non-blocking warnings (e.g., "command may produce large output")
   - Runtime estimate for timeout configuration

## Failure Modes
| Condition | Response |
|---|---|
| Command matches blocked pattern | Reject immediately, report which pattern matched |
| Intent too vague to translate | Return clarification request, not a guess |
| Shell not supported | Default to platform-native shell |
| Argument contains unescaped shell metacharacters | Escape, warn about what was escaped |
| Command not in allowed list | Flag for human_approval, do not auto-execute |
