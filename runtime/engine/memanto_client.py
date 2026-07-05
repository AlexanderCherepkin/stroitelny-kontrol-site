from __future__ import annotations

import importlib.util
import json
import os
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemantoConfig:
    """Runtime configuration for Memanto semantic memory layer.

    Memanto can be reached either via its local REST API (memanto serve)
    or through the optional Python SDKs. If neither is available, the
    client degrades gracefully and stores/retrieves from an in-memory
    fallback so the ReAct loop continues.
    """

    enabled: bool = field(
        default_factory=lambda: os.getenv("MEMANTO_ENABLED", "true").lower()
        not in ("false", "0", "off", "no")
    )
    base_url: str = field(default_factory=lambda: os.getenv("MEMANTO_BASE_URL", "http://127.0.0.1:8000"))
    api_key: str | None = field(default_factory=lambda: os.getenv("MEMANTO_API_KEY") or None)
    agent_id: str = field(default_factory=lambda: os.getenv("MEMANTO_AGENT_ID", "agentic_loop"))
    default_namespace_prefix: str = "memanto_agent_"
    timeout: float = 10.0
    session_token: str | None = None


class MemantoUnavailable:
    """Sentinel returned when Memanto server/SDK is not reachable."""

    pass


class MemantoClient:
    """Lightweight runtime client for the optional Memanto memory layer.

    Mirrors the three primitives from the Memanto design contract:
    remember, recall, answer. If the local Memanto server is not running
    and no SDK is installed, the client falls back to an in-memory store
    so the agent system keeps working.
    """

    _instance: "MemantoClient | None" = None
    _lock = threading.Lock()

    def __new__(cls, config: MemantoConfig | None = None) -> "MemantoClient":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, config: MemantoConfig | None = None):
        if self._initialized:
            return
        self.config = config or MemantoConfig()
        self._fallback_store: list[dict[str, Any]] = []
        self._sdk = self._import_sdk()
        self._initialized = True

    @staticmethod
    def _import_sdk() -> Any:
        """Import optional Memanto SDK modules if installed."""
        if importlib.util.find_spec("memanto") is None:
            return MemantoUnavailable()
        try:
            import memanto
            return memanto
        except Exception:
            return MemantoUnavailable()

    @property
    def is_available(self) -> bool:
        if not self.config.enabled:
            return False
        if not isinstance(self._sdk, MemantoUnavailable):
            return True
        return self._server_reachable()

    def _server_reachable(self) -> bool:
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.config.base_url}/health",
                method="GET",
                headers=self._headers(),
            )
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        if self.config.session_token:
            headers["X-Session-Token"] = self.config.session_token
        return headers

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        import urllib.request

        url = f"{self.config.base_url}{path}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers=self._headers(),
        )
        with urllib.request.urlopen(req, timeout=int(self.config.timeout)) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {"status": "success"}

    def _passthrough(self, operation: str, data: Any) -> dict[str, Any]:
        return {
            "available": False,
            "operation": operation,
            "result": data,
            "note": "Memanto server/SDK unavailable; using in-memory fallback.",
        }

    def _namespace(self, agent_id: str | None = None) -> str:
        return f"{self.config.default_namespace_prefix}{agent_id or self.config.agent_id}"

    def _fallback_remember(self, record: dict[str, Any]) -> dict[str, Any]:
        record.setdefault("id", f"fallback-{len(self._fallback_store)}")
        self._fallback_store.append(record)
        return {
            "available": False,
            "operation": "remember",
            "id": record["id"],
            "status": "fallback_stored",
            "note": "Memanto unavailable; memory kept in local fallback store.",
        }

    def _fallback_recall(self, query: str, limit: int) -> dict[str, Any]:
        # Simple substring match over fallback store
        matches = [
            {
                "id": rec.get("id"),
                "title": rec.get("title"),
                "content": rec.get("content"),
                "type": rec.get("type"),
                "tags": rec.get("tags", []),
                "similarity": 1.0,
            }
            for rec in self._fallback_store
            if query.lower() in rec.get("content", "").lower()
            or query.lower() in rec.get("title", "").lower()
        ][:limit]
        return {
            "available": False,
            "operation": "recall",
            "results": matches,
            "total_found": len(matches),
            "note": "Memanto unavailable; searched in-memory fallback store.",
        }

    def create_agent(
        self,
        agent_id: str | None = None,
        description: str = "Agentic Loop memory agent",
        pattern: str = "multi_agent",
    ) -> dict[str, Any]:
        if not self.is_available:
            return self._passthrough("create_agent", {"agent_id": agent_id})
        try:
            if not isinstance(self._sdk, MemantoUnavailable):
                # SDK path not yet implemented; fall through to REST
                pass
            return self._request(
                "POST",
                "/api/v1/agents",
                {
                    "agent_id": agent_id or self.config.agent_id,
                    "description": description,
                    "pattern": pattern,
                },
            )
        except Exception as exc:
            return self._passthrough("create_agent", {"error": str(exc)})

    def remember(
        self,
        content: str,
        title: str | None = None,
        type: str = "fact",
        tags: list[str] | None = None,
        confidence: float = 0.8,
        agent_id: str | None = None,
        actor_id: str | None = None,
        source: str = "agent",
        source_ref: str | None = None,
    ) -> dict[str, Any]:
        """Store a memory record. Falls back to in-memory store if Memanto is down."""
        if not self.is_available:
            record = {
                "title": title or content[:80],
                "content": content,
                "type": type,
                "tags": tags or [],
                "confidence": confidence,
                "agent_id": agent_id or self.config.agent_id,
                "actor_id": actor_id or "agentic_loop",
                "source": source,
                "source_ref": source_ref,
            }
            return self._fallback_remember(record)

        try:
            payload = {
                "content": content,
                "title": title or content[:80],
                "type": type,
                "tags": tags or [],
                "confidence": confidence,
                "agent_id": agent_id or self.config.agent_id,
                "actor_id": actor_id or "agentic_loop",
                "source": source,
                "source_ref": source_ref,
            }
            return self._request("POST", "/api/v1/memory/remember", payload)
        except Exception as exc:
            return self._passthrough("remember", {"error": str(exc)})

    def recall(
        self,
        query: str,
        agent_id: str | None = None,
        type: list[str] | None = None,
        tags: list[str] | None = None,
        limit: int = 5,
        min_confidence: float | None = None,
    ) -> dict[str, Any]:
        """Retrieve relevant memories. Falls back to substring search if Memanto is down."""
        if not self.is_available:
            return self._fallback_recall(query, limit)

        try:
            payload: dict[str, Any] = {
                "query": query,
                "limit": limit,
            }
            if agent_id:
                payload["agent_id"] = agent_id
            if type:
                payload["type"] = type if isinstance(type, list) else [type]
            if tags:
                payload["tags"] = tags
            if min_confidence is not None:
                payload["min_confidence"] = min_confidence
            return self._request("POST", "/api/v1/memory/recall", payload)
        except Exception as exc:
            return self._passthrough("recall", {"error": str(exc)})

    def answer(
        self,
        query: str,
        agent_id: str | None = None,
        type: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a grounded answer from memory. Falls back to empty response if Memanto is down."""
        if not self.is_available:
            return {
                "available": False,
                "operation": "answer",
                "answer": "",
                "note": "Memanto unavailable; cannot generate grounded answer.",
            }

        try:
            payload: dict[str, Any] = {
                "query": query,
            }
            if agent_id:
                payload["agent_id"] = agent_id
            if type:
                payload["type"] = type if isinstance(type, list) else [type]
            if tags:
                payload["tags"] = tags
            return self._request("POST", "/api/v1/memory/answer", payload)
        except Exception as exc:
            return self._passthrough("answer", {"error": str(exc)})

    def stats(self) -> dict[str, Any]:
        """Return availability and fallback store size."""
        return {
            "available": self.is_available,
            "enabled": self.config.enabled,
            "base_url": self.config.base_url,
            "agent_id": self.config.agent_id,
            "fallback_entries": len(self._fallback_store),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.is_available,
            "enabled": self.config.enabled,
            "base_url": self.config.base_url,
            "agent_id": self.config.agent_id,
        }
