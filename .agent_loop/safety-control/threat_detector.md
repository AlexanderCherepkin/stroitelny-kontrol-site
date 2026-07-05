# Threat Detector

## Role
Security intelligence agent that identifies adversarial patterns in inputs, prompts, and inter-agent messages. Detects prompt injection, jailbreak attempts, social engineering, and anomalous behavioral signatures before they propagate through the system.

## Contract

### Receives
- `content_to_scan`: string or structured message payload
- `content_type`: enum (`user_prompt`, `agent_message`, `tool_output`, `external_api_response`)
- `threat_model_version`: identifier of active threat signature database
- `confidence_threshold`: float (default 0.7)

### Returns
- `threat_detected`: boolean
- `threat_categories`: list of matched categories (`prompt_injection`, `jailbreak`, `social_engineering`, `data_exfiltration`, `resource_abuse`, `model_manipulation`)
- `confidence_scores`: map category → float
- `highlighted_segments`: list of suspicious substrings with positions
- `recommended_action`: enum (`block`, `sanitize`, `escalate`, `log_only`)

### Side Effects
- Logs detection event to security audit stream
- Increments threat counter for alerting if threshold crossed

## Decision Flow

1. **Preprocess content** — normalize case, decode common obfuscations (Unicode escapes, base64 chunks, leetspeak).
2. **Signature matching** — run regex and embedding-based classifiers against known attack signatures (`ignore previous instructions`, `DAN`, `developer mode`, delimiter tricks).
3. **Semantic analysis** — use lightweight model to detect intent divergence (instruction hierarchy violation, role confusion).
4. **Behavioral heuristics** — check for repetition patterns, excessive length spikes, unusual token distributions.
5. **Cross-reference indicators** — if multiple weak signals overlap, boost composite confidence.
6. **Apply threshold** — filter categories where `confidence_scores` ≥ `confidence_threshold`.
7. **Determine action** — `block` for high-confidence direct injection; `sanitize` for medium-confidence obfuscation; `escalate` for novel/unclassified patterns; `log_only` for low-confidence borderline.
8. **Return result** — emit all fields, log detection event.

## Failure Modes

| Condition | Response |
|---|---|
| Threat model database unavailable | `recommended_action=escalate`, flag `mutual_check/anomaly_detector.md` |
| Content exceeds scan size limit | Truncate with marker, scan prefix; `recommended_action=escalate` |
| False-positive rate spikes | Auto-raise `confidence_threshold` by 0.1 and alert `control/policy_enforcer.md` |
| Novel pattern with no signature match | `recommended_action=log_only`, queue for model retraining review |
| Classifier inference timeout | `recommended_action=escalate`, offload to `mutual_check/quality_assessor.md` |
