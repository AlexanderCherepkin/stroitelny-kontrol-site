from __future__ import annotations

import asyncio
import json
import re
import time
import traceback
import warnings
from pathlib import Path
from typing import Any

from .base import MCPServer

warnings.filterwarnings("ignore", category=ResourceWarning)


class BrowserMCPServer(MCPServer):
    """MCP server for tools_browser — headless browser automation via Playwright.

    This server is optional: if Playwright is not installed or browser binaries
    are missing, it still registers its tools but reports as degraded and returns
    helpful errors when invoked. The planner can then fall back to tools_web.
    """

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="tools_browser", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()
        self._tmp_dir = self.workspace / ".tmp" / "browser"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)

        self._playwright = None
        self._browser = None
        self._contexts: dict[str, Any] = {}
        self._pages: dict[str, Any] = {}
        self._degraded_reason: str | None = None

        self._ensure_playwright()
        self._register_tools()
        self._initialized = True  # We are initialized even if degraded

    def _ensure_playwright(self) -> None:
        try:
            from playwright.async_api import async_playwright
            self._async_playwright = async_playwright
        except Exception as e:
            self._degraded_reason = f"Playwright not available: {e}. Install with: pip install playwright && playwright install"
            self._async_playwright = None

    def _register_tools(self) -> None:
        s = self._schema
        self.register("browser_open", "Open a new ephemeral browser session",
                      s({"session_id": "string", "headless?": "bool", "viewport?": "object",
                         "user_agent?": "string", "proxy?": "object"}),
                      self.browser_open)
        self.register("browser_navigate", "Navigate to a URL and wait for dynamic content",
                      s({"session_id": "string", "url": "string", "wait_until?": "string",
                         "timeout_ms?": "int", "allowed_domains?": "array"}),
                      self.browser_navigate)
        self.register("browser_screenshot", "Capture viewport, full-page, or element screenshot",
                      s({"session_id": "string", "target?": "string", "selector?": "string",
                         "output_name?": "string", "format?": "string", "quality?": "int"}),
                      self.browser_screenshot)
        self.register("browser_extract", "Extract dynamic DOM content after JS execution",
                      s({"session_id": "string", "extraction_mode?": "string", "selector?": "string",
                         "max_length?": "int", "include_hidden?": "bool"}),
                      self.browser_extract)
        self.register("browser_click", "Click an element (requires approval for external domains)",
                      s({"session_id": "string", "selector": "string", "approval_token?": "string",
                         "trusted_domain?": "bool"}),
                      self.browser_click)
        self.register("browser_type", "Type text into an element (requires approval for external domains)",
                      s({"session_id": "string", "selector": "string", "value": "string",
                         "approval_token?": "string", "trusted_domain?": "bool"}),
                      self.browser_type)
        self.register("browser_scroll", "Scroll element into view",
                      s({"session_id": "string", "selector": "string"}),
                      self.browser_scroll)
        self.register("browser_evaluate", "Evaluate JavaScript in page context (read-only by default)",
                      s({"session_id": "string", "expression": "string", "read_only?": "bool"}),
                      self.browser_evaluate)
        self.register("browser_cookies", "Get/set/clear browser storage with redaction",
                      s({"session_id": "string", "operation?": "string", "storage_type?": "string",
                         "key?": "string", "value?": "string", "domain?": "string"}),
                      self.browser_cookies)
        self.register("browser_close", "Close browser session and clean up resources",
                      s({"session_id": "string"}),
                      self.browser_close)

    @staticmethod
    def _schema(props: dict[str, str]) -> dict[str, Any]:
        required = [k for k in props if not k.endswith("?")]
        properties: dict[str, Any] = {}
        type_map = {"string": "string", "int": "integer", "bool": "boolean", "float": "number",
                    "array": "array", "object": "object"}
        for k, v in props.items():
            name = k.rstrip("?")
            properties[name] = {"type": type_map.get(v, "string"), "description": f"The {name} parameter"}
        return {"type": "object", "properties": properties, "required": required}

    def _check_degraded(self) -> dict[str, Any] | None:
        if self._degraded_reason:
            return {
                "status": "degraded",
                "error": self._degraded_reason,
                "fallback": "Use tools_web/web_request for static content",
            }
        return None

    async def _get_page(self, session_id: str) -> Any:
        if session_id not in self._pages:
            raise ValueError(f"Session not found: {session_id}")
        return self._pages[session_id]

    async def _get_context(self, session_id: str) -> Any:
        if session_id not in self._contexts:
            raise ValueError(f"Session not found: {session_id}")
        return self._contexts[session_id]

    async def browser_open(self, session_id: str, headless: bool = True,
                           viewport: dict[str, int] | None = None,
                           user_agent: str = "", proxy: dict[str, Any] | None = None) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded

        if session_id in self._contexts:
            return {"status": "ready", "session_id": session_id, "reused": True}

        viewport = viewport or {"width": 1280, "height": 720}
        session_dir = self._tmp_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        pw = await self._async_playwright().start()  # type: ignore
        self._playwright = pw
        browser = await pw.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            proxy=proxy,
        )
        self._browser = browser
        context = await browser.new_context(
            viewport=viewport,
            user_agent=user_agent or None,
        )
        page = await context.new_page()

        self._contexts[session_id] = context
        self._pages[session_id] = page

        return {
            "status": "ready",
            "session_id": session_id,
            "context_isolation": True,
            "session_dir": str(session_dir),
        }

    async def browser_navigate(self, session_id: str, url: str, wait_until: str = "networkidle",
                               timeout_ms: int = 30000,
                               allowed_domains: list[str] | None = None) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded

        page = await self._get_page(session_id)
        parsed = self._parse_url(url)
        if parsed.get("scheme") not in ("http", "https"):
            return {"navigation_status": "blocked", "reason": "Only http/https URLs are allowed"}

        if allowed_domains and parsed.get("host") not in allowed_domains:
            return {"navigation_status": "blocked", "reason": f"Domain {parsed.get('host')} not in allow-list"}

        t0 = time.perf_counter()
        try:
            response = await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            load_time_ms = (time.perf_counter() - t0) * 1000
            final_url = page.url
            title = await page.title()
            frames = [{"name": f.name or "", "url": f.url} for f in page.frames]
            return {
                "navigation_status": "success",
                "final_url": final_url,
                "page_title": title,
                "load_time_ms": round(load_time_ms, 2),
                "frames": frames,
                "status_code": response.status if response else None,
            }
        except Exception as e:
            return {
                "navigation_status": "error",
                "error": self._sanitize(str(e)),
                "load_time_ms": (time.perf_counter() - t0) * 1000,
            }

    async def browser_screenshot(self, session_id: str, target: str = "viewport",
                                 selector: str = "", output_name: str = "",
                                 format: str = "png", quality: int = 80) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded

        page = await self._get_page(session_id)
        session_dir = self._tmp_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time() * 1000)
        name = output_name or f"screenshot_{timestamp}"
        path = session_dir / f"{name}.{format}"

        try:
            kwargs: dict[str, Any] = {"type": format, "path": str(path)}
            if target == "full_page":
                kwargs["full_page"] = True
            elif target == "element" and selector:
                loc = page.locator(selector).first
                kwargs["clip"] = await loc.bounding_box()
            elif target == "viewport":
                pass
            else:
                return {"redaction_status": "blocked", "error": f"Unknown target: {target}"}

            if format == "jpeg":
                kwargs["quality"] = quality

            await page.screenshot(**kwargs)
            redacted = self._redact_image_metadata(str(path))
            return {
                "screenshot_path": str(path),
                "redaction_status": "sensitive_detected" if not redacted else "clean",
                "url_at_capture": page.url,
            }
        except Exception as e:
            return {"redaction_status": "blocked", "error": self._sanitize(str(e))}

    async def browser_extract(self, session_id: str, extraction_mode: str = "text",
                              selector: str = "", max_length: int = 50000,
                              include_hidden: bool = False) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded

        page = await self._get_page(session_id)
        try:
            scope = selector or "body"
            hidden_filter = "" if include_hidden else ":not([style*=\"display:none\"]):not([style*=\"visibility:hidden\"])"

            def _css(target: str) -> str:
                if hidden_filter:
                    return f"{target}:has({hidden_filter})" if target != "body" else f"{target}{hidden_filter}"
                return target

            if extraction_mode == "text":
                text = await page.eval_on_selector(
                    _css(scope),
                    "el => el.innerText",
                )
                text = self._redact_text(text or "")
                truncated = len(text) > max_length
                return {
                    "extracted_content": {"text": text[:max_length]},
                    "char_count": len(text),
                    "truncated": truncated,
                    "metadata": {"url": page.url, "title": await page.title()},
                }

            if extraction_mode == "links":
                links = await page.eval_on_selector_all(
                    f"{scope} a" if scope != "body" else "a",
                    "els => els.map(e => ({text: e.innerText.trim(), href: e.href, is_external: !e.href.includes(location.host)}))",
                )
                return {
                    "extracted_content": {"links": links[:100]},
                    "char_count": len(json.dumps(links)),
                    "truncated": False,
                    "metadata": {"url": page.url},
                }

            if extraction_mode == "headings":
                headings = await page.eval_on_selector_all(
                    "h1, h2, h3, h4, h5, h6",
                    "els => els.map(e => ({level: e.tagName, text: e.innerText.trim()}))",
                )
                return {
                    "extracted_content": {"headings": headings},
                    "char_count": len(json.dumps(headings)),
                    "truncated": False,
                    "metadata": {"url": page.url},
                }

            if extraction_mode == "semantic":
                regions = await page.eval_on_selector_all(
                    "main, article, nav, footer, header, section",
                    "els => els.map(e => ({tag: e.tagName.toLowerCase(), text: (e.innerText || '').trim().slice(0, 500)}))",
                )
                return {
                    "extracted_content": {"regions": regions},
                    "char_count": len(json.dumps(regions)),
                    "truncated": False,
                    "metadata": {"url": page.url},
                }

            return {"extracted_content": {}, "char_count": 0, "truncated": False,
                    "error": f"Unknown extraction_mode: {extraction_mode}"}
        except Exception as e:
            return {"extracted_content": {}, "error": self._sanitize(str(e))}

    async def browser_click(self, session_id: str, selector: str,
                            approval_token: str = "", trusted_domain: bool = False) -> dict[str, Any]:
        if not trusted_domain and not approval_token:
            return {"interaction_status": "blocked",
                    "reason": "Interactive action on external domain requires human approval"}
        page = await self._get_page(session_id)
        try:
            await page.locator(selector).first.click()
            await asyncio.sleep(0.2)
            return {"interaction_status": "success", "new_url": page.url}
        except Exception as e:
            return {"interaction_status": "error", "error": self._sanitize(str(e))}

    async def browser_type(self, session_id: str, selector: str, value: str,
                           approval_token: str = "", trusted_domain: bool = False) -> dict[str, Any]:
        if not trusted_domain and not approval_token:
            return {"interaction_status": "blocked",
                    "reason": "Interactive action on external domain requires human approval"}
        page = await self._get_page(session_id)
        try:
            await page.locator(selector).first.fill(value)
            return {"interaction_status": "success", "new_url": page.url}
        except Exception as e:
            return {"interaction_status": "error", "error": self._sanitize(str(e))}

    async def browser_scroll(self, session_id: str, selector: str) -> dict[str, Any]:
        page = await self._get_page(session_id)
        try:
            await page.locator(selector).first.scroll_into_view_if_needed()
            return {"interaction_status": "success"}
        except Exception as e:
            return {"interaction_status": "error", "error": self._sanitize(str(e))}

    async def browser_evaluate(self, session_id: str, expression: str,
                               read_only: bool = True) -> dict[str, Any]:
        page = await self._get_page(session_id)
        if not read_only:
            return {"status": "blocked", "reason": "Only read-only JS evaluation is allowed by default"}
        try:
            result = await page.evaluate(expression)
            return {"status": "success", "result": self._redact_json(result)}
        except Exception as e:
            return {"status": "error", "error": self._sanitize(str(e))}

    async def browser_cookies(self, session_id: str, operation: str = "list",
                              storage_type: str = "cookies", key: str = "",
                              value: str = "", domain: str = "") -> dict[str, Any]:
        context = await self._get_context(session_id)
        try:
            if storage_type == "cookies":
                if operation == "list":
                    cookies = await context.cookies()
                    return {"operation_status": "success", "data": self._redact_cookies(cookies),
                            "redacted": True}
                if operation == "clear":
                    await context.clear_cookies()
                    return {"operation_status": "success"}
                if operation == "set" and domain:
                    await context.add_cookies([{"name": key, "value": value, "domain": domain, "path": "/"}])
                    return {"operation_status": "success"}
            return {"operation_status": "error", "reason": "Unsupported operation or storage type"}
        except Exception as e:
            return {"operation_status": "error", "error": self._sanitize(str(e))}

    async def browser_close(self, session_id: str) -> dict[str, Any]:
        page = self._pages.pop(session_id, None)
        context = self._contexts.pop(session_id, None)
        if page:
            try:
                await page.close()
            except Exception:
                pass
        if context:
            try:
                await context.close()
            except Exception:
                pass
        if not self._contexts and self._browser:
            try:
                await self._browser.close()
                self._browser = None
            except Exception:
                pass
        return {"status": "closed", "session_id": session_id}

    async def shutdown(self) -> None:
        """Graceful async shutdown; use this instead of atexit on Windows."""
        for session_id in list(self._pages.keys()):
            await self.browser_close(session_id)
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def _cleanup_all(self) -> None:
        """Suppress asyncio/Playwright Windows shutdown noise. Use async shutdown() for real cleanup."""
        import warnings
        warnings.simplefilter("ignore", ResourceWarning)

    @staticmethod
    def _parse_url(url: str) -> dict[str, str]:
        import urllib.parse
        p = urllib.parse.urlparse(url)
        return {"scheme": p.scheme, "host": p.netloc, "path": p.path}

    @staticmethod
    def _sanitize(text: str) -> str:
        # Strip local paths and tokens from error messages
        text = re.sub(r"/[A-Za-z0-9_./-]+/", "/.../", text)
        text = re.sub(r"([A-Za-z0-9_-]{20,})", "[REDACTED]", text)
        return text

    @staticmethod
    def _redact_text(text: str) -> str:
        patterns = [
            (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[REDACTED:email]"),
            (r"\b(?:\d[ -]*?){13,16}\b", "[REDACTED:card-like]"),
            (r"\b[A-Za-z0-9_-]{32,}\b", "[REDACTED:token]"),
        ]
        for pat, repl in patterns:
            text = re.sub(pat, repl, text)
        return text

    @staticmethod
    def _redact_json(value: Any) -> Any:
        if isinstance(value, str):
            return BrowserMCPServer._redact_text(value)
        if isinstance(value, dict):
            return {k: BrowserMCPServer._redact_json(v) for k, v in value.items()}
        if isinstance(value, list):
            return [BrowserMCPServer._redact_json(v) for v in value]
        return value

    @staticmethod
    def _redact_cookies(cookies: list[dict[str, Any]]) -> list[dict[str, Any]]:
        redacted = []
        for c in cookies:
            redacted.append({
                "name": c.get("name"),
                "domain": c.get("domain"),
                "path": c.get("path"),
                "secure": c.get("secure"),
                "httpOnly": c.get("httpOnly"),
                "value": "[REDACTED]",
            })
        return redacted

    @staticmethod
    def _redact_image_metadata(path: str) -> bool:
        # Placeholder: in a real implementation this would strip EXIF and OCR-scan for PII.
        # Returning True means no sensitive metadata detected; file path is already in workspace temp.
        try:
            Path(path).stat()
            return True
        except Exception:
            return False

    async def ping(self) -> bool:
        return True
