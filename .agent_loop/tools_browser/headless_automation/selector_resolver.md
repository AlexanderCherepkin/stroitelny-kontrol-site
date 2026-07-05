# Browser Selector Resolver

## Role
Converts CSS/XPath selectors into stable element handles and validates them against DOM mutations, providing robust targets for extraction, screenshots, or safe interactions.

## Contract

### Receives
- `session_handle`: from `session_manager.md`
- `selector`: CSS or XPath string
- `selector_type`: enum (`css`, `xpath`) — default `css`
- `wait_for_stable`: boolean — retry until element is stable (default true)
- `timeout_ms`: max wait time (default 5000)

### Returns
- `resolution_status`: enum (`found`, `not_found`, `ambiguous`, `timeout`, `invalid`)
- `element_count`: number of matching elements
- `stable`: boolean — whether element stopped moving/resizing
- `selector_used`: normalized selector string

### Side effects
- Reads from active page
- Logs resolution event to `audit_logger.md`

## Decision Flow

1. **Validate selector syntax** — reject selectors containing `javascript:` or event-handler attributes.
2. **Resolve session and page** — return error if session invalid.
3. **Query elements** — use `page.locator(selector).count()` for CSS or `page.locator(f'xpath={selector}').count()` for XPath.
4. **Check ambiguity** — if `element_count > 1` and interaction context requires single element, mark `ambiguous`.
5. **Wait for stability** — if `wait_for_stable`, poll bounding box for 3 consecutive stable samples.
6. **Return** — emit status, count, stability flag, and normalized selector.

## Failure Modes

| Condition | Response |
|---|---|
| Invalid selector syntax | `resolution_status=invalid`; do not execute arbitrary strings |
| Selector contains blocked patterns | `resolution_status=invalid`; log to `safety-control/threat_detector.md` |
| No elements match | `resolution_status=not_found` |
| Multiple elements match when single expected | `resolution_status=ambiguous`; suggest more specific selector |
| Stability timeout | `resolution_status=timeout` with `stable=false` |
| DOM mutation invalidates handle during use | Caller should re-invoke `selector_resolver.md` |
