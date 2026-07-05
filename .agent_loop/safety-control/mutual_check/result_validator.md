# Result Validator

## Role
Final-stage verification agent that validates the correctness, completeness, and deliverability of results before they exit the mutual_check layer. Acts as the last automated gate before control layer or user delivery.

## Contract

### Receives
- `result_payload`: structured or unstructured output from upstream processing
- `validation_schema`: JSON schema, regex, or semantic constraints the result must satisfy
- `validation_level`: enum (`syntax_only`, `structure`, `semantic`, `full`)
- `reference_benchmark`: optional expected result or ground truth for comparison

### Returns
- `validation_status`: enum (`valid`, `valid_with_warnings`, `invalid`, `inconclusive`)
- `check_results`: list of individual checks with pass/fail status and detail
- `warnings`: list of non-fatal issues (deprecated format, missing optional field)
- `failure_reasons`: list of fatal issues if `invalid`
- `confidence`: float

### Side Effects
- Writes validation outcome to `audit_logger.md`
- Updates result quality metrics for feedback loop

## Decision Flow

1. **Select validators** — based on `validation_level`, assemble check pipeline (syntax → structure → semantic → benchmark).
2. **Syntax check** — if payload claims structured format (JSON, XML, YAML), parse and report syntax errors.
3. **Structure check** — validate against `validation_schema`: required fields, types, ranges, enumerations.
4. **Semantic check** — verify that values make sense (non-empty strings where required, URLs are reachable syntactically, dates are plausible).
5. **Benchmark comparison** — if `reference_benchmark` provided, compute similarity or exact match; flag significant divergence.
6. **Warning scan** — identify deprecated patterns, missing optional optimizations, or formatting inconsistencies.
7. **Aggregate verdict** — `valid` if all checks pass with no warnings; `valid_with_warnings` if non-fatal issues; `invalid` if any fatal check fails; `inconclusive` if insufficient data for full validation.
8. **Return result** — emit status, detailed checks, warnings, failures, confidence.

## Failure Modes

| Condition | Response |
|---|---|
| Validation schema malformed or missing | `validation_status=inconclusive`, `failure_reasons=["SCHEMA_UNAVAILABLE"]` |
| Payload size exceeds validator capacity | Stream-validate in chunks; `confidence` reduced by 0.2 |
| Semantic check requires external API that is down | Skip semantic check; `validation_status=valid_with_warnings`, note deferred check |
| Benchmark mismatch but human override present | Honor override; `validation_status=valid_with_warnings`, log override ID |
| Validator internal error | `validation_status=inconclusive`, escalate to `quality_assessor.md` |
