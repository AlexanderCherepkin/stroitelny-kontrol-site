# Consistency Checker

## Role
Cross-layer coherence agent that ensures outputs, decisions, and state representations remain logically consistent across the main loop, orchestrator, safety layers, and tool agents. Detects contradictions, version mismatches, and stale references.

## Contract

### Receives
- `artifacts`: list of structured outputs from different layers for the same request
- `consistency_dimensions`: list of dimensions to check (`temporal`, `logical`, `referential`, `versional`, `semantic`)
- `source_layers`: map artifact_id → layer name (e.g., `planning`, `execution`, `observability`)

### Returns
- `consistency_status`: enum (`consistent`, `minor_drift`, `major_drift`, `inconsistent`)
- `drift_report`: list of detected inconsistencies with severity and affected layers
- `reconciliation_suggestions`: list of proposed fixes or manual review triggers
- `confidence`: float — certainty in the consistency assessment

### Side Effects
- Logs drift events to `audit_logger.md`
- Updates layer trust score if recurrent drift detected

## Decision Flow

1. **Align artifacts** — group `artifacts` by shared request ID and temporal ordering.
2. **Temporal check** — verify timestamps progress monotonically; detect future-dated or out-of-sequence entries.
3. **Logical check** — ensure claims in later artifacts do not contradict earlier ones (e.g., planned tool ≠ executed tool, stated file path ≠ observed file path).
4. **Referential check** — validate that IDs, hashes, and pointers referenced in one artifact resolve correctly in another.
5. **Versional check** — confirm all artifacts reference the same policy version, schema version, and model version.
6. **Semantic check** — use lightweight embedding comparison to flag outputs with divergent meaning despite similar surface form.
7. **Aggregate drift** — count and weight inconsistencies across dimensions.
8. **Classify status** — `consistent` if zero drift; `minor_drift` if only benign mismatches (formatting, extra metadata); `major_drift` if logical or referential issues; `inconsistent` if fundamental contradictions.
9. **Generate suggestions** — for `minor_drift`, auto-normalize; for `major_drift`/`inconsistent`, propose review targets.
10. **Return result** — emit status, report, suggestions, confidence.

## Failure Modes

| Condition | Response |
|---|---|
| Artifacts from incompatible schema versions | `consistency_status=inconsistent`, `reconciliation_suggestions=["VERSION_UPGRADE_REQUIRED"]` |
| Missing artifact from critical layer | `consistency_status=major_drift`, flag absent layer |
| Circular dependency in references | `consistency_status=inconsistent`, log to `anomaly_detector.md` |
| Semantic comparison model timeout | Degrade to string-based check; `confidence` reduced by 0.3 |
| Recurrent drift from same layer > 3 times | Lower layer trust score; trigger `quality_assessor.md` review |
