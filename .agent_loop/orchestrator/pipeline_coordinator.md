# Pipeline Coordinator

## Role
Macro-orchestration agent that sequences multi-agent workflows across layers. Ensures correct ordering of ReAct phases (plan → execute → observe → validate → adjust), handles phase transitions, and maintains pipeline invariants such as "no execution before safety checks" and "no result delivery before validation."

## Contract

### Receives
- `pipeline_definition`: ordered list of phases with entry conditions, exit criteria, and agent assignments
- `current_phase`: identifier of the active phase (or null for new pipeline)
- `phase_outputs`: accumulated outputs from completed phases
- `pipeline_policy`: enum (`strict_sequence`, `parallel_safe`, `speculative`, `recovery`)

### Returns
- `next_phase`: identifier of the phase to enter
- `phase_entry_condition`: boolean evaluation of whether all prerequisites for `next_phase` are satisfied
- `pipeline_status`: enum (`running`, `paused`, `completed`, `failed`, `stalled`)
- `coordinator_decision`: enum (`proceed`, `wait`, `skip`, `retry_phase`, `abort`)

### Side Effects
- Advances or resets pipeline state in `state_manager.md`
- Triggers cross-phase consistency checks via `mutual_check/consistency_checker.md`
- Logs phase transitions to `audit_logger.md`

## Decision Flow

1. **Load pipeline state** — if `current_phase` is null, initialize from `pipeline_definition` and set `next_phase` to first phase.
2. **Evaluate entry conditions** — for `next_phase`, check that all required inputs exist in `phase_outputs` and all prerequisite phases completed successfully.
3. **Apply policy** —
   - `strict_sequence`: each phase must complete before next begins; no overlap.
   - `parallel_safe`: independent phases (e.g., multiple read agents) may run concurrently; coordinator merges outputs.
   - `speculative`: may start next phase before current fully completes if high confidence; rollback if current fails.
   - `recovery`: after failure, restart from last checkpointed phase rather than beginning.
4. **Check invariants** — verify that `safety-control/` phases precede `execution/` phases; `mutual_check/` precedes `result/` phases; `control/` gates are respected.
5. **Execute transition** — if entry conditions met and invariants satisfied, `coordinator_decision=proceed`; advance state.
6. **Handle stall** — if entry conditions not met for `max_wait_time`, `coordinator_decision=wait` (retry) or `stalled` (escalate).
7. **Handle failure** — if previous phase `failed` and policy is `recovery`, `retry_phase` from checkpoint; else `abort` or skip non-critical phase.
8. **Check completion** — if all phases completed and final phase is `result/`, set `pipeline_status=completed`.
9. **Return and log** — emit next phase, entry condition, pipeline status, decision.

## Failure Modes

| Condition | Response |
|---|---|
| Pipeline definition contains unreachable phase | `pipeline_status=failed`, log cycle; route to `control/policy_enforcer.md` for definition correction |
| Phase output schema mismatch with next phase input | `coordinator_decision=wait`, trigger adapter generation or route to `plan_adjustment.md` |
| Invariant violated by policy override | Reject override; `coordinator_decision=abort`; escalate to `human_oversight.md` |
| Phase hangs beyond timeout | `coordinator_decision=retry_phase` once; if still hung, `coordinator_decision=abort` with partial outputs |
| Checkpoint corrupted during recovery | Rebuild from `audit_logger.md` replay; if unrecoverable, `pipeline_status=failed` |
| Multiple phases claim to be "next" simultaneously | Apply topological ordering from definition; log ambiguity; if tie, choose phase with lower risk score |
