# Safety Assessor

## Role
Pre-action risk evaluation agent that computes an overall safety score for a planned operation before execution. Aggregates signals from other safety agents and contextual factors to produce a go/no-go decision with confidence bounds.

## Contract

### Receives
- `proposed_action`: structured operation descriptor (tool name, parameters, target resources)
- `pre_check_signals`: map of upstream safety-agent results (`input_sanitizer.risk_level`, `permission_checker.decision`, `threat_detector.threat_detected`, etc.)
- `execution_environment`: enum (`production`, `staging`, `sandbox`, `user_local`)
- `rollback_available`: boolean indicating whether the operation is reversible

### Returns
- `safety_score`: float 0.0–1.0 (higher = safer)
- `safety_band`: enum (`green`, `yellow`, `orange`, `red`)
- `execution_recommendation`: enum (`proceed`, `proceed_with_caution`, `require_approval`, `block`)
- `concise_rationale`: human-readable summary of scoring drivers
- `mitigations`: list of suggested safeguards if not `proceed`

### Side Effects
- Records assessment to audit log
- Updates per-environment safety statistics

## Decision Flow

1. **Validate inputs** — ensure `pre_check_signals` contains all required keys; if missing, fail closed.
2. **Normalize signals** — convert heterogeneous upstream outputs into numeric risk contributions (0 = no risk, 1 = max risk).
3. **Apply environment weights** — `production` amplifies risk penalties; `sandbox` reduces them; `user_local` applies user-consent modifiers.
4. **Compute composite score** — weighted aggregation: input risk × 0.25 + permission risk × 0.20 + threat risk × 0.20 + command risk × 0.15 + data-leak risk × 0.10 + bias risk × 0.05 + output risk × 0.05.
5. **Adjust for reversibility** — if `rollback_available=true`, nudge score upward by up to 0.15; if irreversible, nudge downward.
6. **Map to band** — `green` (≥0.8), `yellow` (0.6–0.79), `orange` (0.4–0.59), `red` (<0.4).
7. **Determine recommendation** — `proceed` for green; `proceed_with_caution` for yellow; `require_approval` for orange; `block` for red.
8. **Generate mitigations** — for non-green bands, list specific actions (add backup, reduce scope, enable logging, request human review).
9. **Return result** — emit score, band, recommendation, rationale, mitigations.

## Failure Modes

| Condition | Response |
|---|---|
| Missing critical upstream signal | `safety_band=red`, `execution_recommendation=block`, `concise_rationale="INCOMPLETE_ASSESSMENT"` |
| Score calculation numeric error | `safety_band=red`, `execution_recommendation=block`, escalate to `mutual_check/anomaly_detector.md` |
| Environment descriptor unknown | Treat as `production` (fail closed), log classification gap |
| All upstream signals green but irreversible and novel | Downgrade to `yellow` as precaution; add `mitigations=["NOVEL_ACTION_REVIEW"]` |
| Assessment latency exceeds deadline | Return cached conservative estimate (`safety_band=orange`, `require_approval`) |
