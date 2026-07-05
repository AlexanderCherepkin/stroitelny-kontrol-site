# Feedback Aggregator

## Role
Signal synthesis agent that collects, weights, and merges feedback from users, safety agents, quality assessors, and self-monitoring components into a unified improvement directive. Prevents feedback overload and ensures actionable signals reach the right optimization targets.

## Contract

### Receives
- `feedback_items`: list of feedback records with source, timestamp, sentiment, and payload
- `aggregation_scope`: enum (`per_agent`, `per_layer`, `per_request`, `system_wide`)
- `time_window`: period over which to aggregate
- `confidence_weights`: optional source-specific weight map (e.g., user=0.4, safety=0.3, quality=0.3)

### Returns
- `aggregated_feedback`: consolidated feedback with consensus themes and outliers
- `priority_actions`: ranked list of improvements to implement
- `dissenting_signals`: minority viewpoints that may require separate investigation
- `trend_direction`: enum (`improving`, `stable`, `degrading`, `volatile`)

### Side Effects
- Writes aggregation report to memory store for long-term trend analysis
- Triggers policy or model update workflows if consensus emerges

## Decision Flow

1. **Filter and deduplicate** — remove stale or duplicate feedback within `time_window`.
2. **Normalize sentiment** — convert free-text and scores to canonical scale (–1 to +1).
3. **Apply confidence weights** — weight each item by source reliability and recency.
4. **Cluster themes** — group feedback by topic using keyword/embedding clustering.
5. **Compute consensus** — for each theme, calculate weighted average sentiment and variance.
6. **Detect outliers** — flag individual items with sentiment far from cluster mean; preserve as `dissenting_signals`.
7. **Trend analysis** — compare current window to previous window; classify `trend_direction`.
8. **Prioritize actions** — map themes to actionable improvements; rank by impact × feasibility × consensus strength.
9. **Return result** — emit aggregated themes, priority actions, dissenting signals, trend direction.

## Failure Modes

| Condition | Response |
|---|---|
| All feedback sources conflict with no majority | `trend_direction=volatile`, `priority_actions=["MANUAL_REVIEW_REQUIRED"]`, preserve all dissent |
| Feedback stream dominated by single source | Rebalance weights temporarily; flag source diversity issue |
| Theme clustering produces >50 micro-themes | Merge below-threshold clusters into `miscellaneous`; raise granularity parameter |
| Action prioritization produces circular dependencies | Break ties by recency; flag architecture issue to `control/policy_enforcer.md` |
| Memory store write failure | Buffer locally; retry 3×; alert `tools_memory/memory_store/memory_writer.md` if persistent |
