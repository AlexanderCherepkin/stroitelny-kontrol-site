# Environment Result

## Role
Post-execution environment snapshot agent that captures the state of the system after tool invocation completes. Records filesystem changes, process states, environment variables, and configuration deltas to enable verification and rollback.

## Contract

### Receives
- `execution_trace`: from `execution/action_logging.md`
- `snapshot_scope`: enum (`minimal`, `standard`, `comprehensive`) — depth of capture
- `baseline_snapshot`: pre-execution environment state for comparison
- `delta_focus`: optional list of specific paths, variables, or processes to prioritize

### Returns
- `environment_delta`: structured diff of changes between baseline and current state
- `new_artifacts`: list of created or modified files, processes, or configurations with hashes
- `removed_artifacts`: list of deleted items with last-known hash
- `stability_score`: float 0.0–1.0 — measure of environment consistency (no unexpected changes = 1.0)

### Side Effects
- Writes snapshot data to temporary storage for rollback purposes
- May trigger `control/resource_monitor.md` if resource usage changed significantly

## Decision Flow

1. **Select capture scope** — `minimal` captures only changed files; `standard` adds process list and env vars; `comprehensive` includes network state, registry, and loaded modules.
2. **Take post-execution snapshot** — scan filesystem, process table, environment, and network state.
3. **Compare with baseline** — compute symmetric difference against `baseline_snapshot`.
4. **Filter by focus** — if `delta_focus` provided, prioritize and highlight changes in those areas.
5. **Classify changes** — categorize each delta as expected (tool output), suspicious (permission change, unexpected deletion), or benign (timestamp update, cache refresh).
6. **Compute stability score** — 1.0 if only expected changes; deduct for unexpected modifications, new network listeners, or permission escalations.
7. **Flag anomalies** — if `stability_score` < 0.7, emit warning and route to `self_correction/result_validation.md`.
8. **Return** — emit delta, new artifacts, removed artifacts, stability score.

## Failure Modes

| Condition | Response |
|---|---|
| Baseline snapshot missing | Take full snapshot as new baseline; `stability_score=0.5` (unknown deviation); flag incomplete trace |
| Snapshot capture exceeds time budget | Reduce scope to `minimal`; prioritize `delta_focus` items; log truncation |
| Filesystem inaccessible (permission denied) | Report partial snapshot; list blocked paths; `stability_score=0.7` with caveat |
| Baseline and post snapshots have incompatible formats | Normalize both to latest schema; log conversion; continue comparison |
| Environment changed by external process during capture | Detect via timestamp/lock check; if confirmed external, `stability_score=0.6` and flag |
