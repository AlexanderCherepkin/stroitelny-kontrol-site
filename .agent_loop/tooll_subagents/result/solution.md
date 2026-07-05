# Solution

## Role
Final synthesis agent that composes the definitive answer, code, or artifact produced by the entire ReAct cycle into a polished, user-facing deliverable. Ensures the solution directly addresses the original request, incorporates all validated outcomes, and is formatted according to user preferences and domain conventions.

## Contract

### Receives
- `validated_results`: from `self_correction/result_validation.md`
- `execution_trace`: from `execution/tool_invocation.md`
- `observation_artifacts`: from `observability/` agents
- `user_preferences`: style, format, verbosity, and domain conventions from `user/context.md`
- `solution_type`: enum (`code`, `explanation`, `report`, `design_doc`, `patch`, `test_suite`, `data_analysis`)

### Returns
- `solution_payload`: the final deliverable (text, code, structured data, or file references)
- `solution_format`: enum (`markdown`, `json`, `code_block`, `file_tree`, `diff`, `mixed`)
- `completeness_score`: float 0.0–1.0 — how fully the solution addresses the original request
- `references`: list of files modified, sources consulted, or tests run with outcomes
- `known_limitations`: list of caveats or unaddressed edge cases with severity

### Side Effects
- Writes solution to session memory for future context
- May trigger `data_leak_preventer.md` before final delivery
- Logs to `audit_logger.md`

## Decision Flow

1. **Select template** — load domain-specific template for `solution_type` (code: file header + body + tests; explanation: summary + details + examples; report: executive summary + findings + recommendations).
2. **Gather validated outputs** — collect all successful tool outputs, file diffs, test results, and search results from `validated_results`.
3. **Filter by relevance** — discard failed or superseded attempts; include only the final, validated state.
4. **Address user request** — map each part of `original_request` to a section of the solution; ensure nothing asked is omitted.
5. **Apply user preferences** — format: indentation, line length, language (if explanation), comment density, verbosity level. Include/exclude examples based on preference.
6. **Add provenance** — include `references` showing what was changed, what was read, and what tests were run. This builds trust and enables review.
7. **Add limitations** — honestly list `known_limitations` (e.g., "not tested on Windows", "edge case X not handled", "assumes Python 3.10+"). Prevents over-promise.
8. **Check for leaks** — scan `solution_payload` for secrets, credentials, or internal paths before delivery via `data_leak_preventer.md`.
9. **Format output** — convert to `solution_format` ensuring syntax highlighting, proper escaping, and readability.
10. **Return** — emit payload, format, completeness score, references, limitations.

## Failure Modes

| Condition | Response |
|---|---|
| No validated results available | `solution_payload` includes diagnostic apology and request for clarification; `completeness_score=0.0` |
| Solution format unsupported by delivery channel | Auto-convert to nearest supported format; log conversion to `audit_logger.md` |
| Data leak scan flags sensitive content | Redact flagged content with `[REDACTED]` marker; `known_limitations` notes redaction; `completeness_score` reduced |
| User preferences conflict with domain standard (e.g., requested 2-space tabs in Go) | Apply domain standard with note in `known_limitations`; flag preference conflict for future policy review |
| Solution payload exceeds delivery size limit | Generate summary with link to full artifact; `solution_format=markdown` with embedded file references |
