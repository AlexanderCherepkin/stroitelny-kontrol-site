# Action Verifier

## Role
Cross-validation agent that independently confirms whether an executed action produced the expected state change. Compares pre-action and post-action snapshots to detect silent failures, partial successes, and unintended side effects.

## Contract

### Receives
- `action_record`: descriptor of action that was executed (tool, parameters, expected outcome)
- `pre_state_snapshot`: hash or structured state before execution
- `post_state_snapshot`: hash or structured state after execution
- `verification_rules`: list of expected transformations (key changed, file created, process started, etc.)

### Returns
- `verification_status`: enum (`confirmed`, `partial`, `failed`, `inconclusive`)
- `matched_rules`: list of verification rules that passed
- `unmatched_rules`: list of rules that failed or are unverified
- `unexpected_changes`: list of state mutations not covered by any rule
- `delta_summary`: concise diff of relevant state changes

### Side Effects
- Writes verification result to `audit_logger.md`
- Updates per-tool reliability score

## Decision Flow

1. **Normalize snapshots** — parse `pre_state_snapshot` and `post_state_snapshot` into comparable canonical form.
2. **Compute delta** — generate diff of all changed fields, files, processes, or resources.
3. **Evaluate expected rules** — for each `verification_rules`, check if corresponding delta exists with correct direction and magnitude.
4. **Detect unexpected changes** — flag any delta entry not matched by a rule as potential side effect.
5. **Assess severity of unexpected changes** — benign (timestamp update) vs risky (permission change, file deletion outside scope).
6. **Score verification** — `confirmed` if all rules match and no risky unexpected changes; `partial` if most rules match but some benign side effects; `failed` if critical rule unmatched or risky side effect detected; `inconclusive` if snapshots incomplete.
7. **Log and return** — emit full result, write to audit.

## Failure Modes

| Condition | Response |
|---|---|
| Pre-state snapshot missing | `verification_status=inconclusive`, `unmatched_rules=["MISSING_PRE_STATE"]` |
| Snapshot hash mismatch (corruption suspected) | `verification_status=inconclusive`, escalate to `anomaly_detector.md` |
| Verification rule syntax invalid | Skip rule, log parse error; continue with valid rules |
| Post-state unavailable (tool crashed) | `verification_status=failed`, `unmatched_rules=["NO_POST_STATE"]` |
| Unexpected change is irreversible data loss | `verification_status=failed`, immediately alert `control/human_oversight.md` |
