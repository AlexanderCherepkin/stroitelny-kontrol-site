# Runtime Output

## Role
Output capture and analysis agent that collects, parses, and interprets the stdout, stderr, and exit codes produced by executed tools. Transforms raw streams into structured observations that downstream agents can reason about.

## Contract

### Receives
- `raw_output`: stdout and stderr text streams from tool execution
- `exit_code`: integer process exit status or null if not applicable
- `output_type`: enum (`structured_json`, `structured_xml`, `text_log`, `binary`, `mixed`)
- `parse_hint`: optional schema or regex pattern expected in output

### Returns
- `parsed_output`: structured representation of the output (JSON object, log entries, or annotated text)
- `error_indicators`: list of detected errors, warnings, or anomalies with severity and location
- `success_indicators`: list of confirmations, progress markers, or success signatures
- `output_completeness`: enum (`complete`, `truncated`, `corrupted`, `timeout_exceeded`)
- `extracted_metrics`: key-value pairs of quantitative data (timings, counts, percentages)

### Side Effects
- Stores parsed output in session memory for self-correction and result synthesis
- May trigger `self_correction/result_validation.md` if errors detected

## Decision Flow

1. **Detect encoding** — scan for BOM, UTF-8/16 signatures, or common encoding issues; normalize to UTF-8.
2. **Classify completeness** — check for truncation markers, truncation of long lines, or premature termination signals.
3. **Parse structure** — if `output_type` is structured, validate and parse; if text, apply `parse_hint` regexes or heuristics.
4. **Extract error indicators** — scan for keywords (`error`, `exception`, `fatal`, `fail`, `assertion`, `segmentation fault`), stack traces, and non-zero `exit_code`.
5. **Extract success indicators** — scan for keywords (`success`, `pass`, `ok`, `done`, `complete`), progress 100%, and zero `exit_code`.
6. **Extract metrics** — identify and parse numeric patterns: timestamps, durations, percentages, memory usage, file sizes, counts.
7. **Handle binary output** — if `binary`, compute hash and size; defer detailed parsing to specialized agent if needed.
8. **Assess confidence** — if parsing contradicts `exit_code` (errors found but exit=0, or vice versa), flag ambiguity.
9. **Return** — emit parsed output, error/success indicators, completeness, metrics.

## Failure Modes

| Condition | Response |
|---|---|
| Output exceeds memory buffer | Stream-process in chunks; `output_completeness=truncated`; preserve first and last N lines |
| Encoding unrecognizable or mixed | Attempt best-effort decoding; mark uncertain characters; `output_completeness=corrupted` |
| Parse hint contradicts actual output format | Ignore hint; auto-detect format; log mismatch to `feedback_aggregator.md` |
| Binary output misclassified as text | Reclassify; return binary hash; suggest `content_extractor.md` for downstream parsing |
| Exit code missing but process clearly crashed | Infer from signal indicators; `output_completeness=corrupted`; `error_indicators` include crash signature |
