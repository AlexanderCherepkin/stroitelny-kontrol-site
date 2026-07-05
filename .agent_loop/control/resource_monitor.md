# Resource Monitor

## Role
Infrastructure watchdog agent that tracks CPU, memory, disk, GPU, and I/O consumption across all agents. Triggers throttling, preemption, or graceful degradation when resource pressure threatens system stability.

## Contract

### Receives
- `resource_type`: enum (`cpu`, `memory`, `disk`, `gpu`, `io`, `network`)
- `measurement_window`: seconds of data to aggregate
- `alert_thresholds`: map resource_type → percentage or absolute limit
- `auto_scale_policy`: enum (`none`, `throttle`, `preempt`, `notify`)

### Returns
- `pressure_level`: enum (`normal`, `elevated`, `critical`, `emergency`)
- `current_utilization`: map resource_type → percentage or absolute value
- `predicted_trend`: enum (`stable`, `rising`, `spiking`, `recovering`)
- `actions_taken`: list of automated interventions applied
- `top_consumers`: ranked list of agents or processes by resource usage

### Side Effects
- Publishes metrics to time-series store
- Executes throttling or preemption if policy permits
- Notifies `human_oversight.md` if `emergency`

## Decision Flow

1. **Collect metrics** — sample system and per-process counters for `resource_type` over `measurement_window`.
2. **Normalize** — convert raw counters to percentages or rates relative to total capacity.
3. **Detect pressure** — compare against `alert_thresholds`: normal if all below warning; elevated if any exceeds warning; critical if any exceeds critical; emergency if multiple critical or OOM imminent.
4. **Predict trend** — apply exponential smoothing or derivative estimate to classify trajectory.
5. **Identify top consumers** — rank agents by contribution to highest-pressure resource.
6. **Apply auto-scale policy** — if `throttle`, reduce CPU quota or request batch size for top consumers; if `preempt`, pause lowest-priority background agents; if `notify`, emit alert only; if `none`, record only.
7. **Log and return** — emit pressure level, utilization, trend, actions, consumers.

## Failure Modes

| Condition | Response |
|---|---|
| Metric collector fails (kernel module error) | `pressure_level=emergency` as precaution, `actions_taken=["METRIC_FAILSAFE"]` |
| Auto-scale policy attempts to throttle critical agent | Skip critical agent, throttle next highest; alert `human_oversight.md` |
| OOM imminent and preemption list empty | Trigger emergency garbage collection; if still critical, restart lowest-priority agent |
| Disk pressure on log partition | Rotate logs aggressively; if still critical, pause non-essential auditing |
| Resource counter wraps or resets | Detect anomaly via negative delta; discard sample and recalibrate baseline |
