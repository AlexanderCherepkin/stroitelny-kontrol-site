from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .base import MCPServer


class MemantoMCPServer(MCPServer):
    """MCP server that wraps the Memanto semantic memory layer.

    Exposes four tools:
      - memanto_create_agent — ensure the agent namespace exists.
      - memanto_remember     — store a typed memory record.
      - memanto_recall       — retrieve relevant memories.
      - memanto_answer       — generate a grounded answer from memory.

    The server is lazy-loaded and reports degraded if the optional Memanto
    server is not running, so the rest of the system keeps working.
    """

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="memanto", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()
        self._degraded_reason: str | None = None
        self._client: Any = None
        self._ensure_memanto()
        self._register_tools()
        self._initialized = True

    def _ensure_memanto(self) -> None:
        try:
            from runtime.engine.memanto_client import MemantoClient, MemantoConfig

            self._client = MemantoClient(
                MemantoConfig(
                    enabled=os.getenv("MEMANTO_ENABLED", "true").lower()
                    not in ("false", "0", "off", "no"),
                    base_url=os.getenv("MEMANTO_BASE_URL", "http://127.0.0.1:8000"),
                    api_key=os.getenv("MEMANTO_API_KEY") or None,
                    agent_id=os.getenv("MEMANTO_AGENT_ID", "agentic_loop"),
                )
            )
            if not self._client.is_available:
                self._degraded_reason = (
                    "Memanto server is not reachable. Run 'memanto serve' or install memanto."
                )
        except Exception as exc:
            self._degraded_reason = f"Memanto client failed to initialize: {exc}"

    def _register_tools(self) -> None:
        s = self._schema
        self.register(
            "memanto_create_agent",
            "Ensure a Memanto agent namespace exists for the current session.",
            s({
                "agent_id?": "string",
                "description?": "string",
                "pattern?": "string",
            }),
            self.memanto_create_agent,
        )
        self.register(
            "memanto_remember",
            "Store a typed memory record in Memanto for later recall.",
            s({
                "content": "string",
                "title?": "string",
                "type?": "string",
                "tags?": "array",
                "confidence?": "float",
                "agent_id?": "string",
                "actor_id?": "string",
                "source?": "string",
                "source_ref?": "string",
            }),
            self.memanto_remember,
        )
        self.register(
            "memanto_recall",
            "Retrieve relevant memories from Memanto by semantic query.",
            s({
                "query": "string",
                "agent_id?": "string",
                "type?": "array",
                "tags?": "array",
                "limit?": "int",
                "min_confidence?": "float",
            }),
            self.memanto_recall,
        )
        self.register(
            "memanto_answer",
            "Generate a grounded answer from accumulated Memanto memories.",
            s({
                "query": "string",
                "agent_id?": "string",
                "type?": "array",
                "tags?": "array",
            }),
            self.memanto_answer,
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
                "fallback": "Run 'memanto serve' locally or disable MEMANTO_ENABLED.",
            }
        return None

    def memanto_create_agent(
        self,
        agent_id: str = "",
        description: str = "Agentic Loop memory agent",
        pattern: str = "multi_agent",
    ) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        return self._client.create_agent(
            agent_id=agent_id or None,
            description=description,
            pattern=pattern,
        )

    def memanto_remember(
        self,
        content: str,
        title: str = "",
        type: str = "fact",
        tags: list[str] | None = None,
        confidence: float = 0.8,
        agent_id: str = "",
        actor_id: str = "",
        source: str = "agent",
        source_ref: str = "",
    ) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        return self._client.remember(
            content=content,
            title=title or None,
            type=type,
            tags=tags,
            confidence=confidence,
            agent_id=agent_id or None,
            actor_id=actor_id or None,
            source=source,
            source_ref=source_ref or None,
        )

    def memanto_recall(
        self,
        query: str,
        agent_id: str = "",
        type: list[str] | None = None,
        tags: list[str] | None = None,
        limit: int = 5,
        min_confidence: float | None = None,
    ) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        return self._client.recall(
            query=query,
            agent_id=agent_id or None,
            type=type,
            tags=tags,
            limit=limit,
            min_confidence=min_confidence,
        )

    def memanto_answer(
        self,
        query: str,
        agent_id: str = "",
        type: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        return self._client.answer(
            query=query,
            agent_id=agent_id or None,
            type=type,
            tags=tags,
        )

    async def ping(self) -> bool:
        return True
