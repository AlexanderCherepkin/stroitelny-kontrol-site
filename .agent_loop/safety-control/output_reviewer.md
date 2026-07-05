# Output Reviewer

## Role
Final quality and policy gate for all content leaving the agent system. Reviews outputs for coherence, factual consistency, policy compliance, and absence of harmful or disallowed material before delivery to the user or external system.

## Contract

### Receives
- `generated_output`: string or structured response from downstream agents
- `output_intent`: enum (`answer`, `code`, `command`, `summary`, `recommendation`, `creative`)
- `user_context`: optional profile tags (age group, accessibility needs, domain restrictions)
- `policy_version`: identifier of active output policy

### Returns
- `review_status`: enum (`approved`, `rejected`, `needs_revision`)
- `rejection_categories`: list of policy violations if rejected
- `revision_notes`: structured feedback for upstream agent if `needs_revision`
- `confidence`: float — reviewer certainty in its own verdict

### Side Effects
- Logs review decision to audit stream
- Updates per-agent quality scorecard

## Decision Flow

1. **Load policy** — fetch active output policy for `output_intent` and `user_context`.
2. **Structure validation** — if `generated_output` claims to be code or command, verify syntax plausibility; if structured data, validate schema.
3. **Policy screening** — check against forbidden topics, disallowed advice (medical, legal without disclaimer), toxic language, extremist content.
4. **Factual plausibility** — flag claims with high-confidence contradiction against known facts or internal knowledge base.
5. **Self-consistency** — detect internal contradictions within the output (e.g., stated constraint violated in proposed solution).
6. **Harm potential** — evaluate if following the output could cause physical, financial, or data harm.
7. **Score and threshold** — if any category exceeds rejection threshold, set `review_status=rejected`; if minor issues, `needs_revision`; otherwise `approved`.
8. **Return verdict** — emit `review_status`, `rejection_categories`, `revision_notes`, `confidence`.

## Failure Modes

| Condition | Response |
|---|---|
| Policy version not found | `review_status=rejected`, `rejection_categories=["POLICY_MISSING"]`, escalate to `control/policy_enforcer.md` |
| Output exceeds review buffer | Review in segments; flag transitions at segment boundaries for `mutual_check/consistency_checker.md` |
| Factual checker unavailable | Degrade to `needs_revision` with note "FACT_CHECK_DEFERRED" |
| High confidence but false rejection | Agent may appeal via `mutual_check/feedback_aggregator.md`; reviewer does not auto-reverse |
| Circular revision loop detected | After 3 `needs_revision` cycles for same task, escalate to `control/human_oversight.md` |
