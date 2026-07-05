from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .base import MCPServer


class WebMCPServer(MCPServer):
    """MCP server for tools_web — web request pipeline (request-lifecycle)."""

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="tools_web", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()
        self._cache: dict[str, tuple[float, str]] = {}
        self._rate_limiters: dict[str, tuple[int, float]] = {}  # domain -> (count, window_start)

        self.register("build_request", "Build an HTTP request with method, URL, headers, body",
                       self._s({"method": "string", "url": "string", "headers?": "object",
                                "body?": "string", "timeout_ms?": "int"}), self.build_request)
        self.register("add_auth", "Add authentication to request (Bearer, Basic, API key)",
                       self._s({"headers": "object", "auth_type": "string", "credentials": "string"}),
                       self.add_auth)
        self.register("check_network", "Check network connectivity to a URL",
                       self._s({"url": "string", "timeout_ms?": "int"}), self.check_network)
        self.register("check_rate_limit", "Check and enforce rate limits for a domain",
                       self._s({"domain": "string", "max_requests_per_minute?": "int"}),
                       self.check_rate_limit)
        self.register("send_request", "Send an HTTP request and return the response",
                       self._s({"method": "string", "url": "string", "headers?": "object",
                                "body?": "string", "timeout_ms?": "int", "allow_redirects?": "bool"}),
                       self.send_request)
        self.register("parse_response", "Parse HTTP response — status, headers, body",
                       self._s({"response_body": "string", "content_type?": "string",
                                "status_code?": "int"}), self.parse_response)
        self.register("extract_content", "Extract structured content from HTML/JSON/XML response",
                       self._s({"body": "string", "content_type?": "string",
                                "selector?": "string"}), self.extract_content)
        self.register("cache_response", "Cache a response for reuse",
                       self._s({"url": "string", "response": "string", "ttl_seconds?": "int"}),
                       self.cache_response)
        self.register("handle_retry", "Determine retry strategy for failed request",
                       self._s({"url": "string", "status_code": "int", "error?": "string",
                                "attempt": "int"}), self.handle_retry)
        self.register("analyze_error", "Analyze HTTP error response",
                       self._s({"status_code": "int", "response_body?": "string"}), self.analyze_error)

    async def build_request(self, method: str, url: str, headers: dict[str, str] | None = None,
                            body: str = "", timeout_ms: int = 30000) -> dict[str, Any]:
        return {
            "method": method.upper(),
            "url": url,
            "headers": headers or {},
            "body": body,
            "timeout_ms": timeout_ms,
            "parsed_url": urllib.parse.urlparse(url)._asdict() if "://" in url else None,
        }

    async def add_auth(self, headers: dict[str, str], auth_type: str,
                       credentials: str) -> dict[str, Any]:
        h = dict(headers)
        auth_lower = auth_type.lower()
        if auth_lower in ("bearer", "token"):
            h["Authorization"] = f"Bearer {credentials}"
        elif auth_lower == "basic":
            import base64
            encoded = base64.b64encode(credentials.encode()).decode()
            h["Authorization"] = f"Basic {encoded}"
        elif auth_lower == "api_key":
            h["X-API-Key"] = credentials
        return {"headers": h, "auth_type": auth_type}

    async def check_network(self, url: str, timeout_ms: int = 10000) -> dict[str, Any]:
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(url, method="HEAD")
            urllib.request.urlopen(req, timeout=timeout_ms / 1000)
            latency = (time.perf_counter() - t0) * 1000
            return {"url": url, "reachable": True, "latency_ms": latency}
        except Exception as e:
            return {"url": url, "reachable": False, "error": str(e),
                    "latency_ms": (time.perf_counter() - t0) * 1000}

    async def check_rate_limit(self, domain: str, max_requests_per_minute: int = 60) -> dict[str, Any]:
        now = time.time()
        if domain in self._rate_limiters:
            count, window_start = self._rate_limiters[domain]
            if now - window_start > 60:
                count, window_start = 0, now
            if count >= max_requests_per_minute:
                wait = 60 - (now - window_start)
                return {"domain": domain, "allowed": False, "retry_after_seconds": wait,
                        "current_rate": f"{count}/min"}
            self._rate_limiters[domain] = (count + 1, window_start)
        else:
            self._rate_limiters[domain] = (1, now)
        return {"domain": domain, "allowed": True, "current_rate": f"{self._rate_limiters[domain][0]}/min"}

    async def send_request(self, method: str, url: str, headers: dict[str, str] | None = None,
                           body: str = "", timeout_ms: int = 30000,
                           allow_redirects: bool = True) -> dict[str, Any]:
        domain = urllib.parse.urlparse(url).netloc or "unknown"
        rate_check = await self.check_rate_limit(domain)
        if not rate_check["allowed"]:
            return {"error": "Rate limited", **rate_check}

        cache_key = hashlib.md5(f"{method}:{url}:{body}".encode()).hexdigest()
        cached = self._cache.get(cache_key)
        if cached and time.time() - cached[0] < 60:
            return json.loads(cached[1])

        t0 = time.perf_counter()
        try:
            data = body.encode() if body else None
            req = urllib.request.Request(url, data=data, method=method.upper())
            if headers:
                for k, v in headers.items():
                    req.add_header(k, v)
            with urllib.request.urlopen(req, timeout=timeout_ms / 1000) as resp:
                resp_body = resp.read().decode("utf-8", errors="replace")
                latency = (time.perf_counter() - t0) * 1000
                result = {
                    "url": url, "status_code": resp.status,
                    "headers": dict(resp.headers),
                    "body": resp_body[:100000], "body_size": len(resp_body),
                    "latency_ms": latency, "method": method,
                }
            self._cache[cache_key] = (time.time(), json.dumps(result))
            return result
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:10000]
            except Exception:
                pass
            return {"url": url, "status_code": e.code, "error": str(e), "body": err_body,
                    "latency_ms": (time.perf_counter() - t0) * 1000}
        except Exception as e:
            return {"url": url, "error": str(e), "status_code": 0,
                    "latency_ms": (time.perf_counter() - t0) * 1000}

    async def parse_response(self, response_body: str, content_type: str = "",
                             status_code: int = 200) -> dict[str, Any]:
        ct = content_type.lower()
        parsed = None
        if "json" in ct or response_body.strip().startswith("{"):
            try:
                parsed = json.loads(response_body)
                ct = "application/json"
            except json.JSONDecodeError:
                pass
        return {"content_type": ct, "status_code": status_code, "body_length": len(response_body),
                "parsed": parsed is not None, "parsed_type": type(parsed).__name__ if parsed else None}

    async def extract_content(self, body: str, content_type: str = "",
                              selector: str = "") -> dict[str, Any]:
        ct = content_type.lower()
        extracted: dict[str, Any] = {}

        if "json" in ct:
            try:
                data = json.loads(body)
                if selector:
                    parts = selector.split(".")
                    for p in parts:
                        if isinstance(data, dict) and p in data:
                            data = data[p]
                        elif isinstance(data, list) and p.isdigit():
                            data = data[int(p)]
                        else:
                            data = None
                            break
                    extracted["value"] = data
                else:
                    extracted = {"keys": list(data.keys()) if isinstance(data, dict) else [],
                                 "count": len(data) if isinstance(data, list) else 1}
            except json.JSONDecodeError:
                extracted = {"error": "Invalid JSON"}

        elif "html" in ct or body.strip().startswith("<"):
            text = re.sub(r"<[^>]+>", " ", body)
            text = re.sub(r"\s+", " ", text).strip()
            links = re.findall(r'href=[\'"](.+?)[\'"]', body)
            extracted = {"text": text[:5000], "links": links[:50], "link_count": len(links)}

        else:
            extracted = {"preview": body[:1000]}

        return {"content_type": ct, "selector": selector, **extracted}

    async def cache_response(self, url: str, response: str, ttl_seconds: int = 300) -> dict[str, Any]:
        key = hashlib.md5(url.encode()).hexdigest()
        self._cache[key] = (time.time(), response)
        return {"cached": True, "url": url, "ttl_seconds": ttl_seconds}

    async def handle_retry(self, url: str, status_code: int, error: str = "",
                           attempt: int = 1) -> dict[str, Any]:
        MAX_ATTEMPTS = 3
        should_retry = False
        wait_ms = 0

        if status_code in (429, 503):
            should_retry = attempt < MAX_ATTEMPTS
            wait_ms = min(1000 * (2 ** attempt), 30000)
        elif status_code in (500, 502, 504):
            should_retry = attempt < MAX_ATTEMPTS
            wait_ms = 500 * (2 ** attempt)
        elif error and status_code == 0:
            should_retry = attempt < MAX_ATTEMPTS
            wait_ms = 1000 * attempt

        return {"url": url, "attempt": attempt, "should_retry": should_retry,
                "wait_ms": wait_ms, "next_attempt": attempt + 1 if should_retry else None}

    async def analyze_error(self, status_code: int, response_body: str = "") -> dict[str, Any]:
        error_map = {
            400: {"type": "bad_request", "description": "The server cannot process the request (client error)"},
            401: {"type": "unauthorized", "description": "Authentication required or failed"},
            403: {"type": "forbidden", "description": "Authenticated but not authorized for this resource"},
            404: {"type": "not_found", "description": "The requested resource does not exist"},
            408: {"type": "timeout", "description": "The server timed out waiting for the request"},
            429: {"type": "rate_limited", "description": "Too many requests — slow down",
                  "retry_after": "Check Retry-After header"},
            500: {"type": "server_error", "description": "Internal server error — retry may help"},
            502: {"type": "bad_gateway", "description": "Upstream server error — retry may help"},
            503: {"type": "unavailable", "description": "Service temporarily unavailable — retry later"},
        }

        info = error_map.get(status_code, {"type": "unknown", "description": f"HTTP {status_code}"})
        return {"status_code": status_code, **info,
                "body_preview": response_body[:500] if response_body else ""}

    @staticmethod
    def _s(props: dict[str, str]) -> dict[str, Any]:
        required = [k for k in props if not k.endswith("?")]
        properties = {}
        for k, v in props.items():
            name = k.rstrip("?")
            type_map = {"string": "string", "int": "integer", "bool": "boolean", "float": "number", "array": "array", "object": "object"}
            properties[name] = {"type": type_map.get(v, "string"), "description": f"The {name} parameter"}
        return {"type": "object", "properties": properties, "required": required}
