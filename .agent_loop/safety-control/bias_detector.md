# Bias Detector

## Role
Fairness and impartiality agent that audits outputs and decisions for demographic, ideological, or representational bias. Ensures equitable treatment across gender, ethnicity, age, disability, and other protected dimensions.

## Contract

### Receives
- `target_text`: string or structured content to analyze
- `analysis_scope`: enum (`output`, `decision_rationale`, `recommendation`, `user_facing_summary`)
- `protected_dimensions`: list of dimensions to check (default: gender, ethnicity, age, disability, religion, socioeconomic)
- `domain_context`: enum (`hiring`, `lending`, `healthcare`, `education`, `general`, `creative`)

### Returns
- `bias_detected`: boolean
- `dimension_scores`: map dimension → float score (0.0 = neutral, 1.0 = strong bias)
- `flagged_phrases`: list of biased expressions with suggested neutral alternatives
- `overall_score`: aggregated bias metric
- `recommendation`: enum (`pass`, `revise`, `escalate`)

### Side Effects
- Logs bias metrics to fairness audit stream
- Contributes to periodic fairness dashboard

## Decision Flow

1. **Tokenize and segment** — split `target_text` into sentences or decision units for granular analysis.
2. **Dimension-specific scanning** — for each `protected_dimension`, load associated lexical and semantic bias detectors.
3. **Stereotype detection** — flag stereotypical associations (e.g., gendered pronouns for occupations, racially coded adjectives).
4. **Representation analysis** — check for under-representation or over-representation of groups in lists, examples, or recommendations.
5. **Framing analysis** — detect differential framing (positive framing for one group, negative for another in comparable contexts).
6. **Score aggregation** — compute per-dimension and overall scores using calibrated weights for `domain_context`.
7. **Threshold application** — `revise` if any dimension exceeds medium threshold; `escalate` if any exceeds high threshold or multiple dimensions are flagged; `pass` if all below threshold.
8. **Generate alternatives** — for each `flagged_phrases`, produce 1–2 neutral rephrasing suggestions.
9. **Return result** — emit all scores, flagged phrases, alternatives, and recommendation.

## Failure Modes

| Condition | Response |
|---|---|
| Bias model unavailable | `recommendation=escalate`, route to `mutual_check/quality_assessor.md` for manual review |
| Domain context unrecognized | Default to `general` weights; log unknown domain for model update |
| Text in unsupported language | `recommendation=escalate`, flag for multilingual model expansion |
| Dimension score calibration drift | Auto-adjust threshold by comparing rolling average; alert `control/policy_enforcer.md` |
| Suggested alternative introduces new bias | Filter alternatives through secondary scan; if still biased, omit suggestion |
