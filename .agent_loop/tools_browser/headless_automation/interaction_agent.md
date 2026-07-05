# Browser Interaction Agent

## Role
Performs safe, gated interactions (click, type, scroll, form submit) on a web page. All interactions require explicit approval unless the domain is in a trusted allow-list.

## Contract

### Receives
- `session_handle`: from `session_manager.md`
- `action`: enum (`click`, `type`, `scroll`, `hover`, `submit`, `select`)
- `selector`: target element selector
- `value`: string for `type`/`select` actions
- `approval_token`: from `tooll_subagents/execution/human_approval.md` when required
- `trusted_domain`: boolean — set by `control/network_guard.md`

### Returns
- `interaction_status`: enum (`success`, `blocked`, `timeout`, `error`)
- `new_url`: URL after action (if navigation occurred)
- `validation_message`: confirmation or error detail

### Side effects
- May mutate page state (form values, scroll position)
- May trigger navigation
- Logs action to `audit_logger.md`

## Decision Flow

1. **Check approval requirements** — if `action` is interactive and `trusted_domain=false`, require `approval_token`; without it, return `interaction_status=blocked`.
2. **Resolve selector** — call `selector_resolver.md`; if not found, return error.
3. **Validate safety** — ensure target is visible, enabled, and not inside `iframe` with foreign origin unless explicitly allowed.
4. **Execute action**:
   - `click`: `locator.click()`;
   - `type`: `locator.fill(value)`;
   - `scroll`: `locator.scroll_into_view_if_needed()`;
   - `hover`: `locator.hover()`;
   - `submit`: click submit button or call `form.requestSubmit()`;
   - `select`: `locator.select_option(value)`.
5. **Wait for navigation/update** — short wait for network idle after action.
6. **Return** — emit status, new URL, and validation message.

## Failure Modes

| Condition | Response |
|---|---|
| No human approval for interactive action on external domain | `interaction_status=blocked`; route to `execution/human_approval.md` |
| Target element not found or not actionable | `interaction_status=error`; re-resolve via `selector_resolver.md` |
| Action triggers unexpected file download | Cancel download; `interaction_status=error` |
| Action triggers popup/new window | Block popup; `interaction_status=error` |
| Form submission leads to disallowed domain | `interaction_status=blocked`; route to `control/network_guard.md` |
| CAPTCHA or login wall detected post-action | `interaction_status=blocked`; route to `captcha_challenge_agent.md` |
