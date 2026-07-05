# Browser DOM Extractor

## Role
Extracts semantically useful text, links, tables, and structural regions from a dynamically rendered page after JavaScript execution completes.

## Contract

### Receives
- `session_handle`: from `session_manager.md`
- `extraction_mode`: enum (`text`, `links`, `tables`, `headings`, `semantic`, `all`)
- `selector`: optional CSS selector to restrict extraction
- `max_length`: max characters to return (default 50000)
- `include_hidden`: boolean — include visually hidden elements (default false)

### Returns
- `extracted_content`: structured content dict by mode
- `char_count`: total characters extracted
- `truncated`: boolean — whether content exceeded `max_length`
- `metadata`: page title, url, extracted_at timestamp

### Side effects
- Reads from active page; no writes
- Logs extraction event to `audit_logger.md`
- May call `safety-control/data_leak_preventer.md` for outgoing content

## Decision Flow

1. **Resolve session and page** — return error if session invalid.
2. **Wait for stability** — perform short `page.wait_for_load_state('networkidle')` if not already idle.
3. **Select scope** — use `selector` if provided; otherwise document root.
4. **Extract by mode**:
   - `text`: visible text content;
   - `links`: list of `{text, href, is_external}`;
   - `tables`: list of `{headers, rows}`;
   - `headings`: hierarchy h1–h6 with text;
   - `semantic`: regions (main, article, nav, footer) with summaries;
   - `all`: combined dict of all modes.
5. **Redact sensitive fragments** — scan for tokens, emails, credit cards; replace with `[REDACTED:type]`.
6. **Truncate** — if `char_count > max_length`, trim and set `truncated=true`.
7. **Return** — emit structured content, counts, and metadata.

## Failure Modes

| Condition | Response |
|---|---|
| Session invalid | Return error; request `session_manager.md` |
| Page not loaded | Return empty content with `metadata.url=null` |
| Selector invalid or matches nothing | Return empty content for that mode; other modes still return data |
| Extracted content contains unredacted secrets | Re-run `data_leak_preventer.md`; if still failing, return `extracted_content` with `[REDACTED:blocked]` |
| JavaScript evaluation error during extraction | Capture static DOM fallback; log to `error_handler.md` |
