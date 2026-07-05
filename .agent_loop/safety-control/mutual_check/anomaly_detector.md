# Anomaly Detector

## Role
Behavioral forensics agent that identifies unusual patterns in agent decisions, resource consumption, latency distributions, and inter-agent communication. Acts as the early-warning system for compromise, misconfiguration, or emergent bugs.

## Contract

### Receives
- `observation_window`: time range and granularity of data to analyze
- `observation_type`: enum (`traffic`, `latency`, `errors`, `decisions`, `resource_usage`, `communication_graph`)
- `detection_sensitivity`: enum (`low`, `medium`, `high`, `adaptive`)
- `reference_model`: optional pre-trained baseline or historical distribution

### Returns
- `anomaly_detected`: boolean
- `anomaly_score`: float 0.0–1.0
- `anomaly_descriptions`: list of human-readable anomaly summaries with affected components
- `recommended_response`: enum (`log`, `alert`, `throttle`, `isolate`, `investigate`)
- `contributing_features`: ranked list of variables driving the anomaly score

### Side Effects
- Writes anomaly record to `audit_logger.md`
- Updates reference model if `adaptive` sensitivity enabled
- Triggers downstream alerts or isolation hooks

## Decision Flow

1. **Fetch data** — retrieve `observation_type` metrics for `observation_window`.
2. **Select model** — load `reference_model` if provided; otherwise use rolling window statistical model.
3. **Feature extraction** — compute derived features (rate of change, burstiness, cross-correlation, graph centrality).
4. **Score observations** — run statistical tests (z-score, IQR, isolation forest, autoencoder reconstruction error) per feature.
5. **Aggregate anomaly score** — combine per-feature scores with learned weights; apply `detection_sensitivity` threshold.
6. **Cluster anomalies** — group temporally or spatially related anomalies into single incident description.
7. **Determine response** — `log` if score < 0.5; `alert` if 0.5–0.7; `throttle` if 0.7–0.85; `isolate` if >0.85 and targeted at single component; `investigate` if distributed or novel.
8. **Update model** — if `adaptive`, ingest current window into model (excluding confirmed anomalies).
9. **Return result** — emit detection flag, score, descriptions, response, features.

## Failure Modes

| Condition | Response |
|---|---|
| Reference model corrupted | Rebuild from last 7 days of clean data; `detection_sensitivity` temporarily lowered to `low` |
| Data stream contains confirmed false positives | Tag and exclude from model; do not suppress alert pipeline |
| Anomaly score spikes due to legitimate burst (e.g., batch job) | Cross-reference with `quota_manager.md` scheduled jobs; downgrade if explained |
| Detection latency exceeds real-time requirement | Switch to lightweight heuristic mode; queue deep analysis for async completion |
| Cascading anomalies trigger overlapping responses | Deduplicate by root component; execute most restrictive response only |
