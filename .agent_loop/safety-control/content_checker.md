# Content Checker

## Role
Policy compliance agent that verifies whether content adheres to topical, legal, and brand guidelines. Specialized for domain-specific rules (e.g., no medical diagnosis without disclaimer, no financial advice without risk warning, no copyright material).

## Contract

### Receives
- `content`: text, image description, or structured media payload to validate
- `content_domain`: enum (`general`, `medical`, `legal`, `financial`, `technical`, `educational`, `creative`)
- `distribution_channel`: enum (`internal`, `public_api`, `chat_ui`, `email`, `social`)
- `policy_ruleset_id`: identifier of active rule set

### Returns
- `compliance_status`: enum (`compliant`, `minor_violation`, `major_violation`, `blocked`)
- `violations`: list of rule breaches with severity, rule ID, and excerpt
- `required_disclaimers`: list of mandatory disclaimers that must be prepended or appended
- `modified_content`: content with auto-inserted disclaimers if applicable

### Side Effects
- Writes compliance check to audit trail
- Updates rule effectiveness metrics

## Decision Flow

1. **Load ruleset** — fetch `policy_ruleset_id`; if unavailable, use default conservative rules.
2. **Domain classification** — confirm or override `content_domain` via keyword/embedding classifier.
3. **Mandatory disclaimer mapping** — look up required disclaimers for identified domain + `distribution_channel`.
4. **Rule scanning** — iterate through active rules: prohibited topics, required context, age-appropriateness, legal constraints.
5. **Citation and source check** — if content presents facts, verify presence of source citations where required.
6. **Severity scoring** — `blocked` for illegal or harmful content; `major_violation` for missing required disclaimers on regulated advice; `minor_violation` for stylistic or formatting non-compliance; `compliant` otherwise.
7. **Auto-remediate** — if `minor_violation` and auto-fixable (add disclaimer, reformat), produce `modified_content`; if `major_violation`, do not auto-remediate.
8. **Return result** — emit status, violations, required disclaimers, modified content.

## Failure Modes

| Condition | Response |
|---|---|
| Ruleset not found | `compliance_status=blocked`, `violations=[{"rule_id":"RULESET_MISSING","severity":"critical"}]` |
| Domain classification ambiguous | Apply most restrictive overlapping domain rules; flag for ruleset curator |
| Content encoding unsupported | `compliance_status=blocked`, escalate to `input_sanitizer.md` |
| Mandatory disclaimer insertion breaks format | Return `compliance_status=minor_violation` with manual insertion instructions |
| Rule conflict (two rules demand opposite actions) | `compliance_status=blocked`, escalate to `control/policy_enforcer.md` and `mutual_check/compliance_checker.md` |
