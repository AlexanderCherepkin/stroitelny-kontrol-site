from __future__ import annotations

import importlib.util
import json
import os
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HeadroomConfig:
    """Runtime configuration for Headroom context compression.

    Values are read from environment variables by default and can be overridden
    per session. The package remains optional: if headroom-ai is not installed,
    the client reports unavailable and returns passthrough results.
    """

    enabled: bool = field(default_factory=lambda: os.getenv("HEADROOM_ENABLED", "true").lower() not in ("false", "0", "off", "no"))
    default_model: str = "claude-sonnet-4-5-20250929"
    min_tokens_to_compress: int = 250
    target_ratio: float | None = None
    session_ttl: int = 3600
    proxy_url: str = field(default_factory=lambda: os.getenv("HEADROOM_PROXY_URL", "http://127.0.0.1:8787"))


class HeadroomUnavailable:
    """Sentinel returned when headroom-ai is not installed."""

    pass


class HeadroomClient:
    """Lightweight wrapper around the optional headroom-ai Python SDK.

    Provides explicit compression, retrieval, session stats, and a shared
    context for multi-agent handoffs. Every method degrades gracefully: if the
    package is missing, it returns a passthrough result with `available=False`
    instead of raising, so the ReAct loop can continue without Headroom.
    """

    _instance: "HeadroomClient | None" = None
    _lock = threading.Lock()

    def __new__(cls, config: HeadroomConfig | None = None) -> "HeadroomClient":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, config: HeadroomConfig | None = None):
        if self._initialized:
            return
        self.config = config or HeadroomConfig()
        self._headroom = self._import_headroom()
        self._shared_context: Any = None
        self._initialized = True

    @staticmethod
    def _import_headroom() -> Any:
        """Import headroom only if it is installed; otherwise return sentinel."""
        if importlib.util.find_spec("headroom") is None:
            return HeadroomUnavailable()
        try:
            import headroom

            return headroom
        except Exception:
            return HeadroomUnavailable()

    @property
    def is_available(self) -> bool:
        return not isinstance(self._headroom, HeadroomUnavailable) and self.config.enabled

    def _passthrough(self, content: Any) -> dict[str, Any]:
        """Return a result that leaves content untouched."""
        return {
            "available": False,
            "compressed": content,
            "hash": "",
            "original_tokens": 0,
            "compressed_tokens": 0,
            "tokens_saved": 0,
            "savings_percent": 0.0,
            "transforms": [],
            "note": "headroom-ai is not installed or disabled; content passed through unchanged.",
        }

    def compress_text(
        self,
        text: str,
        model: str | None = None,
        target_ratio: float | None = None,
    ) -> dict[str, Any]:
        """Compress a single text fragment (e.g. tool output, log, file snippet).

        Wraps the text as a tool message and runs it through Headroom's pipeline.
        """
        if not self.is_available:
            return self._passthrough(text)

        messages = [{"role": "tool", "content": text}]
        return self.compress_messages(
            messages,
            model=model,
            target_ratio=target_ratio,
        )

    def compress_messages(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        target_ratio: float | None = None,
    ) -> dict[str, Any]:
        """Compress a list of chat messages before sending them to an LLM."""
        if not self.is_available:
            return self._passthrough(messages)

        try:
            kwargs: dict[str, Any] = {}
            if target_ratio is not None:
                kwargs["target_ratio"] = target_ratio
            result = self._headroom.compress(
                messages,
                model=model or self.config.default_model,
                **kwargs,
            )
            compressed_content = result.messages[0].get("content", messages)
            if not isinstance(compressed_content, str):
                compressed_content = json.dumps(compressed_content)

            store = self._get_store()
            hash_key = store.store(
                original=json.dumps(messages, ensure_ascii=False),
                compressed=compressed_content,
                original_tokens=result.tokens_before,
                compressed_tokens=result.tokens_after,
                compression_strategy="runtime_compress",
                ttl=self.config.session_ttl,
            )

            return {
                "available": True,
                "compressed": result.messages,
                "hash": hash_key,
                "original_tokens": result.tokens_before,
                "compressed_tokens": result.tokens_after,
                "tokens_saved": max(0, result.tokens_before - result.tokens_after),
                "savings_percent": round((1 - result.tokens_after / result.tokens_before) * 100, 1)
                if result.tokens_before > 0
                else 0.0,
                "transforms": result.transforms_applied,
            }
        except Exception as exc:
            return {
                "available": True,
                "error": str(exc),
                **self._passthrough(messages),
            }

    def retrieve(self, hash_key: str) -> dict[str, Any]:
        """Retrieve original uncompressed content by hash from local CCR store."""
        if not self.is_available:
            return {
                "available": False,
                "found": False,
                "hash": hash_key,
                "original_content": None,
                "error": "headroom-ai is not installed or disabled.",
            }

        try:
            store = self._get_store()
            entry = store.retrieve(hash_key)
            if entry:
                return {
                    "available": True,
                    "found": True,
                    "hash": hash_key,
                    "original_content": entry.original_content,
                    "source": "local",
                }
            return {
                "available": True,
                "found": False,
                "hash": hash_key,
                "original_content": None,
                "error": "Content not found. It may have expired or the hash may be incorrect.",
            }
        except Exception as exc:
            return {
                "available": True,
                "found": False,
                "hash": hash_key,
                "original_content": None,
                "error": str(exc),
            }

    def stats(self) -> dict[str, Any]:
        """Return Headroom session statistics if the package is installed."""
        if not self.is_available:
            return {
                "available": False,
                "compressions": 0,
                "retrievals": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_tokens_saved": 0,
                "savings_percent": 0.0,
            }

        try:
            store = self._get_store()
            store_stats = store.get_stats()
            return {
                "available": True,
                "store": {
                    "entries": store_stats.get("entry_count", 0),
                    "max_entries": store_stats.get("max_entries", 0),
                },
            }
        except Exception as exc:
            return {"available": True, "error": str(exc)}

    def shared_context(self) -> Any:
        """Return a SharedContext instance for compressed inter-agent handoffs.

        Lazily initialized and reused across the session. If headroom is not
        installed, returns None; callers must fall back to plain context.
        """
        if not self.is_available:
            return None
        if self._shared_context is None:
            self._shared_context = self._headroom.SharedContext(
                model=self.config.default_model,
                ttl=self.config.session_ttl,
            )
        return self._shared_context

    def _get_store(self) -> Any:
        """Get the shared compression store singleton."""
        from headroom.cache.compression_store import get_compression_store

        return get_compression_store()

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.is_available,
            "enabled": self.config.enabled,
            "default_model": self.config.default_model,
        }
