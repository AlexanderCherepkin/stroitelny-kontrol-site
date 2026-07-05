# Policy Enforcer

## Role
Runtime rule engine that interprets and applies active governance policies across all layers. Resolves conflicts between overlapping rules, dynamically updates policy state, and ensures every agent action complies with the latest version of system-wide regulations.

## Contract

### Receives
- `action_descriptor`: structured description of action to evaluate
- `policy_context`: enum (`security`, `resource`, `privacy`, `operational`, `ethical`)
- `active_policies`: list of policy IDs to apply
- `project_rules`: dict | None — lightweight rules from `project_rules.md`
- `conflict_resolution_mode`: enum (`most_restrictive`, `hierarchy`, `timestamp`, `human_override`)

### Returns
- `enforcement_decision`: enum (`allow`, `deny`, `conditional_allow`, `policy_gap`)
- `applicable_rules`: list of rules that matched the action
- `conflicts_resolved`: list of rule pairs where conflict was detected and resolved
- `conditional_constraints`: list of additional requirements if `conditional_allow`
- `policy_version`: version identifier of the policy set used

### Side Effects
- Logs enforcement decision to `audit_logger.md`
- Updates rule hit-frequency metrics
- Queues policy-gap reports for governance review

## Decision Flow

1. **Load policies** — fetch `active_policies`; if empty or missing, use `project_rules` as lightweight fallback policy source; if `project_rules.ponytail` exists, merge it as an `operational` policy context. If both are missing, substitute with default conservative rule.
2. **Parse action** — decompose `action_descriptor` into subject, verb, object, and environment tags.
3. **Match rules** — evaluate each rule in loaded policies against parsed action; collect all matching rules.
4. **Detect conflicts** — if matching rules demand opposite outcomes, apply `conflict_resolution_mode`.
5. **Apply resolution** — `most_restrictive` chooses deny over allow; `hierarchy` uses policy priority order; `timestamp` prefers newer rule; `human_override` checks for approved exception ticket. If `project_rules` conflicts with an explicit `active_policy`, apply `most_restrictive` regardless of `conflict_resolution_mode`.
6. **Check conditions** — if matched rule has predicates (time-of-day, location, quota), evaluate them.
7. **Determine decision** — `allow` if all matched rules allow unconditionally; `deny` if any rule denies and not overridden; `conditional_allow` if allow rules have unmet predicates; `policy_gap` if no rules match and no default.
8. **Return and log** — emit decision, rules, conflicts, constraints, version.

## Failure Modes

| Condition | Response |
|---|---|
| Policy store unreachable | `enforcement_decision=deny`, `policy_version="EMERGENCY_DEFAULT"` |
| Circular policy inheritance | Break loop at depth 10; log unresolved inheritance to `audit_logger.md` |
| Human override ticket expired or forged | Reject override, `enforcement_decision=deny`, escalate to `human_oversight.md` |
| Rule syntax error (unparsable condition) | Skip malformed rule; continue with valid rules; flag for policy curator |
| `project_rules` conflicts with explicit `active_policies` | Apply `most_restrictive`; log conflict; include both rule sets in `conflicts_resolved` |
| Policy gap for critical action type | `enforcement_decision=policy_gap`, block action, queue urgent policy review |
| `project_rules.ponytail` mode conflicts with `active_policies` | Apply `most_restrictive`; log conflict; prefer explicit active policy over project-rules default |

