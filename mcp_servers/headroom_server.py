from __future__ import annotations

import importlib.util
import json
import os
import traceback
import warnings
from pathlib import Path
from typing import Any

from .base import MCPServer

warnings.filterwarnings("ignore", category=ResourceWarning)


class HeadroomMCPServer(MCPServer):
    """MCP server that wraps Headroom context compression.

    Exposes three tools:
      - headroom_compress  — compress content and store the original locally.
      - headroom_retrieve  — retrieve the original content by hash.
      - headroom_stats     — report session compression statistics.

    The server is lazy-loaded and reports degraded if the optional `headroom-ai`
    package is not installed, so the rest of the system keeps working.
    """

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="headroom", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()
        self._degraded_reason: str | None = None
        self._headroom: Any = None
        self._ensure_headroom()
        self._register_tools()
        self._initialized = True

    def _ensure_headroom(self) -> None:
        if importlib.util.find_spec("headroom") is None:
            self._degraded_reason = "headroom-ai is not installed (pip install headroom-ai[proxy,mcp])"
            return
        try:
            import headroom

            self._headroom = headroom
        except Exception as exc:
            self._degraded_reason = f"headroom-ai import failed: {exc}"

    def _register_tools(self) -> None:
        s = self._schema
        self.register(
            "headroom_compress",
            "Compress content to save context-window tokens. Stores original for later retrieval.",
            s({"content": "string", "model?": "string", "target_ratio?": "float"}),
            self.headroom_compress,
        )
        self.register(
            "headroom_retrieve",
            "Retrieve original uncompressed content by hash returned from headroom_compress.",
            s({"hash": "string"}),
            self.headroom_retrieve,
        )
        self.register(
            "headroom_stats",
            "Show Headroom compression statistics: compressions, tokens saved, estimated cost.",
            s({}),
            self.headroom_stats,
        )

    @staticmethod
    def _schema(props: dict[str, str]) -> dict[str, Any]:
        required = [k for k in props if not k.endswith("?")]
        properties: dict[str, Any] = {}
        type_map = {
            "string": "string",
            "int": "integer",
            "bool": "boolean",
            "float": "number",
            "array": "array",
            "object": "object",
        }
        for k, v in props.items():
            name = k.rstrip("?")
            properties[name] = {"type": type_map.get(v, "string"), "description": f"The {name} parameter"}
        return {"type": "object", "properties": properties, "required": required}

    def _check_degraded(self) -> dict[str, Any] | None:
        if self._degraded_reason:
            return {
                "status": "degraded",
                "error": self._degraded_reason,
                "fallback": "Install headroom-ai[proxy,mcp] or disable HEADROOM_ENABLED",
            }
        return None

    def headroom_compress(
        self,
        content: str,
        model: str = "",
        target_ratio: float | None = None,
    ) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded

        try:
            messages = [{"role": "tool", "content": content}]
            kwargs: dict[str, Any] = {}
            if target_ratio is not None:
                kwargs["target_ratio"] = target_ratio
            result = self._headroom.compress(
                messages,
                model=model or os.getenv("HEADROOM_MODEL", "claude-sonnet-4-5-20250929"),
                **kwargs,
            )
            compressed_content = result.messages[0].get("content", content)
            if not isinstance(compressed_content, str):
                compressed_content = json.dumps(compressed_content)

            store = self._get_store()
            hash_key = store.store(
                original=content,
                compressed=compressed_content,
                original_tokens=result.tokens_before,
                compressed_tokens=result.tokens_after,
                compression_strategy="mcp_compress",
                ttl=int(os.getenv("HEADROOM_SESSION_TTL", "3600")),
            )

            return {
                "status": "success",
                "compressed": compressed_content,
                "hash": hash_key,
                "original_tokens": result.tokens_before,
                "compressed_tokens": result.tokens_after,
                "tokens_saved": max(0, result.tokens_before - result.tokens_after),
                "savings_percent": round((1 - result.tokens_after / result.tokens_before) * 100, 1)
                if result.tokens_before > 0
                else 0.0,
                "transforms": result.transforms_applied,
                "note": f"Original stored with hash={hash_key}. Use headroom_retrieve to get full content later.",
            }
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }

    def headroom_retrieve(self, hash: str) -> dict[str, Any]:  # noqa: A002 — hash is the tool parameter name
        degraded = self._check_degraded()
        if degraded:
            return degraded

        try:
            store = self._get_store()
            entry = store.retrieve(hash)
            if entry:
                return {
                    "status": "success",
                    "hash": hash,
                    "found": True,
                    "original_content": entry.original_content,
                    "source": "local",
                }
            return {
                "status": "not_found",
                "hash": hash,
                "found": False,
                "error": "Content not found. It may have expired or the hash may be incorrect.",
                "hint": "Re-read the file or re-run the command that produced the compressed content.",
            }
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }

    def headroom_stats(self) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded

        try:
            store = self._get_store()
            store_stats = store.get_stats()
            return {
                "status": "success",
                "store": {
                    "entries": store_stats.get("entry_count", 0),
                    "max_entries": store_stats.get("max_entries", 0),
                },
                "note": "Install headroom-ai CLI or run a proxy for full session stats.",
            }
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }

    def _get_store(self) -> Any:
        """Lazy-load the shared Headroom compression store."""
        from headroom.cache.compression_store import get_compression_store

        return get_compression_store()

    async def ping(self) -> bool:
        return True
