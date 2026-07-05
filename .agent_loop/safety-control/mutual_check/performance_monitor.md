# Performance Monitor

## Role
Observability agent that continuously tracks latency, throughput, error rates, and resource utilization across all layers of the Agentic Loop. Provides early warning of degradation and triggers scaling or throttling decisions.

## Contract

### Receives
- `metric_stream`: time-series data points from instrumented agents and infrastructure
- `alert_rules`: list of thresholds and window configurations (e.g., p99 latency > 500 ms over 2 min)
- `baseline_profile`: historical normal operating ranges per layer and time-of-day
- `sampling_rate`: float (0.0–1.0) for high-cardinality metrics

### Returns
- `health_status`: enum (`healthy`, `degraded`, `unhealthy`, `unknown`)
- `active_alerts`: list of currently firing alert rules with severity
- `top_bottlenecks`: ranked list of slowest or most resource-intensive components
- `recommendations`: list of suggested actions (scale up, throttle, investigate)
- `snapshot_metrics`: current values for key indicators

### Side Effects
- Writes metrics to time-series database
- Triggers paging or notification channels if alert severity = critical
- Updates auto-scaling signals

## Decision Flow

1. **Ingest and sample** — accept `metric_stream`; downsample if cardinality exceeds budget using `sampling_rate`.
2. **Normalize and tag** — attach layer, agent, and request-id tags for dimensional analysis.
3. **Compute aggregates** — calculate percentiles, rates, and ratios over configured windows.
4. **Compare against baseline** — detect deviations from `baseline_profile` using statistical process control (z-score, Holt-Winters).
5. **Evaluate alert rules** — check each rule against current aggregates; mark firing or resolved.
6. **Correlate anomalies** — if multiple alerts fire simultaneously, compute likely root component via dependency graph.
7. **Classify health** — `healthy` if all metrics within baseline; `degraded` if minor thresholds breached; `unhealthy` if critical thresholds breached or error rate spikes; `unknown` if data insufficient.
8. **Generate recommendations** — propose scaling for capacity, throttling for overload, or deep-dive for unknown root cause.
9. **Emit and store** — return result, write metrics, fire alerts.

## Failure Modes

| Condition | Response |
|---|---|
| Metric stream silent > expected interval | `health_status=unknown`, `active_alerts=["METRIC_STREAM_SILENT"]` |
| Baseline profile missing for new layer | Build provisional baseline from first 100 observations; flag low confidence |
| Alert rule evaluation loops or contradictions | Disable conflicting rules; notify `control/policy_enforcer.md` |
| Time-series database write failure | Buffer in-memory for 60 s; if still down, spill to local file and alert |
| False positive burst (>5 alerts/min) | Auto-silence non-critical alerts for 5 min; trigger `anomaly_detector.md` review |
