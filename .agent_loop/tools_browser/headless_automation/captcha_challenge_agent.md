# Browser CAPTCHA Challenge Agent

## Role
Detects CAPTCHA, login walls, and other human-verification obstacles during browser automation. Never attempts to solve them automatically; always escalates to human approval.

## Contract

### Receives
- `session_handle`: from `session_manager.md`
- `page_snapshot`: DOM text and screenshot metadata from `dom_extractor.md` / `screenshot_agent.md`
- `detection_confidence_threshold`: float (default 0.7)

### Returns
- `challenge_detected`: boolean
- `challenge_type`: enum (`captcha`, `login_wall`, `two_factor`, `rate_limit`, `unknown`, `none`)
- `confidence`: float 0.0–1.0
- `recommended_action`: enum (`escalate_human`, `continue`, `abort`)

### Side effects
- Reads page content and metadata
- Logs detection event to `audit_logger.md`
- May invoke `tooll_subagents/execution/human_approval.md`

## Decision Flow

1. **Scan page content** — look for keywords (`captcha`, `recaptcha`, `hcaptcha`, `g-recaptcha`, `verify you are human`, `login required`, `2fa`, `otp`, `rate limited`).
2. **Inspect selectors** — detect known CAPTCHA iframe hosts or challenge containers.
3. **Score confidence** — combine keyword and selector signals; if `confidence >= detection_confidence_threshold`, set `challenge_detected=true`.
4. **Classify challenge type** — map detected signals to `challenge_type`.
5. **Determine action** — always `recommended_action=escalate_human` for CAPTCHA/login/2FA; `abort` for repeated rate-limit; `continue` if confidence below threshold.
6. **Return** — emit detection result and recommended action.

## Failure Modes

| Condition | Response |
|---|---|
| Auto-solve attempted by caller | Reject and log to `safety-control/threat_detector.md`; `recommended_action=abort` |
| Challenge detected but classification uncertain | `challenge_type=unknown`; `recommended_action=escalate_human` |
| Human approval unavailable | `recommended_action=abort`; preserve page state for manual review |
| False positive on common UI text | Lower confidence; `recommended_action=continue` if below threshold |
