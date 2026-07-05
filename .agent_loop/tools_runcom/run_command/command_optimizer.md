# Command Optimizer

## Role
Cross-cutting strategist for the command execution pipeline. Analyzes the command, configures safety layers, estimates resource usage, and selects the optimal execution profile. The conductor before the first process is spawned.

## Contract
- **Receives**: `{ command, intent, constraints: { timeout_ms, max_output_bytes, allow_network, allow_fs_writes } }`
- **Returns**: `{ plan: { pipeline: [agent], sandbox_config, env_strategy, timeout_ms, estimated_risk: "low"|"medium"|"high"|"critical" } }`
- **Side effects**: none (planning only)

## Decision Flow

1. **Risk classification**
   - **Low risk**: pure read operation, no network, no writes. `ls`, `cat`, `grep`, `git status`, `echo`.
   - **Medium risk**: package manager query, build dry-run. `npm outdated`, `cargo check`.
   - **High risk**: writes files, installs packages, network access. `npm install`, `pip install`, `git pull`.
   - **Critical risk**: arbitrary script execution, system modification. `curl | sh`, `sudo`, `rm -rf`, `chmod`.

2. **Configure sandbox**
   - Low risk → `network: "none"`, `fs: "read_only"` for CWD
   - Medium risk → `network: "restricted"`, `fs: "read_write"` for specific dirs
   - High risk → `network: "restricted"` + explicit host whitelist, `fs: "read_write"` with backup
   - Critical risk → require human_approval before any configuration is applied

3. **Pipeline configuration**
   - Safety chain (always): command_builder → sandbox_agent → env_manager → timeout_watcher
   - Execution: executor_agent → output_collector
   - Post-execution: error_analyzer
   - File operations (conditional): write_planner → write_executor
   - If command is read-only → skip write_planner and write_executor entirely

4. **Resource estimation**
   - Time: use command_builder's estimate, configure timeout_watcher with 3× margin
   - Output: estimate based on command type (log output = large, status output = small)
   - Memory: estimate based on command type (compiler = high, ls = negligible)

5. **Validate plan against constraints**
   - Estimated memory > sandbox limit → increase sandbox memory or reject
   - Estimated time > timeout → increase timeout or reject
   - Risk level "critical" + no human approval → block, escalate

## Failure Modes
| Condition | Response |
|---|---|
| Risk is "critical" but no approval configured | Block execution, require human_approval gate |
| Constraints incompatible (network needed, network forbidden) | Flag conflict, let caller resolve |
| Command type unknown (custom tool) | Assume high risk, apply strictest safety defaults |
| All strategies blocked by constraints | Return best-effort plan with violation flags |
