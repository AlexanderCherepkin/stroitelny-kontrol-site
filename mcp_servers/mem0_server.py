from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .base import MCPServer


class Mem0MCPServer(MCPServer):
    """MCP server that wraps the Mem0 long-term memory layer.

    Exposes four tools:
      - mem0_add      — store a memory or conversation turn.
      - mem0_search   — retrieve relevant memories by query.
      - mem0_get_all  — list memories for the current entity scope.
      - mem0_delete   — delete a memory by id.

    The server is lazy-loaded and reports degraded if the optional Mem0
    package/API is not available, so the rest of the system keeps working.
    """

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="mem0", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()
        self._degraded_reason: str | None = None
        self._client: Any = None
        self._ensure_mem0()
        self._register_tools()
        self._initialized = True

    def _ensure_mem0(self) -> None:
        try:
            from runtime.engine.mem0_client import Mem0Client, Mem0Config

            self._client = Mem0Client(
                Mem0Config(
                    enabled=os.getenv("MEM0_ENABLED", "true").lower()
                    not in ("false", "0", "off", "no"),
                    api_key=os.getenv("MEM0_API_KEY") or None,
                    host=os.getenv("MEM0_HOST") or None,
                    vector_store_provider=os.getenv("MEM0_VECTOR_STORE", "chroma"),
                    vector_store_path=os.getenv("MEM0_VECTOR_STORE_PATH", str(self.workspace / "memory_storage")),
                    llm_provider=os.getenv("MEM0_LLM_PROVIDER", "openai"),
                    llm_model=os.getenv("MEM0_LLM_MODEL", "gpt-4o-mini"),
                    embedder_provider=os.getenv("MEM0_EMBEDDER_PROVIDER", "openai"),
                    user_id=os.getenv("MEM0_USER_ID", "agentic_loop"),
                    agent_id=os.getenv("MEM0_AGENT_ID", "agentic_loop"),
                    app_id=os.getenv("MEM0_APP_ID") or None,
                    run_id=os.getenv("MEM0_RUN_ID") or None,
                )
            )
            if not self._client.is_available:
                self._degraded_reason = (
                    "Mem0 is not available. Install mem0ai, set MEM0_API_KEY, or enable a local vector store."
                )
        except Exception as exc:
            self._degraded_reason = f"Mem0 client failed to initialize: {exc}"

    def _register_tools(self) -> None:
        s = self._schema
        self.register(
            "mem0_add",
            "Store a memory or conversation turn in Mem0.",
            s({
                "messages": "string",
                "user_id?": "string",
                "agent_id?": "string",
                "run_id?": "string",
                "metadata?": "object",
                "infer?": "bool",
            }),
            self.mem0_add,
        )
        self.register(
            "mem0_search",
            "Retrieve relevant memories from Mem0 by semantic query.",
            s({
                "query": "string",
                "user_id?": "string",
                "agent_id?": "string",
                "run_id?": "string",
                "limit?": "int",
                "threshold?": "float",
            }),
            self.mem0_search,
        )
        self.register(
            "mem0_get_all",
            "List all memories for the current entity scope.",
            s({
                "user_id?": "string",
                "agent_id?": "string",
                "run_id?": "string",
                "limit?": "int",
            }),
            self.mem0_get_all,
        )
        self.register(
            "mem0_delete",
            "Delete a specific memory from Mem0 by id.",
            s({"memory_id": "string"}),
            self.mem0_delete,
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
                "fallback": "Install mem0ai, set MEM0_API_KEY, or disable MEM0_ENABLED.",
            }
        return None

    def mem0_add(
        self,
        messages: str,
        user_id: str = "",
        agent_id: str = "",
        run_id: str = "",
        metadata: dict[str, Any] | None = None,
        infer: bool = True,
    ) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        return self._client.add(
            messages=messages,
            user_id=user_id or None,
            agent_id=agent_id or None,
            run_id=run_id or None,
            metadata=metadata,
            infer=infer,
        )

    def mem0_search(
        self,
        query: str,
        user_id: str = "",
        agent_id: str = "",
        run_id: str = "",
        limit: int = 5,
        threshold: float = 0.1,
    ) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        return self._client.search(
            query=query,
            user_id=user_id or None,
            agent_id=agent_id or None,
            run_id=run_id or None,
            limit=limit,
            threshold=threshold,
        )

    def mem0_get_all(
        self,
        user_id: str = "",
        agent_id: str = "",
        run_id: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        return self._client.get_all(
            user_id=user_id or None,
            agent_id=agent_id or None,
            run_id=run_id or None,
            limit=limit,
        )

    def mem0_delete(self, memory_id: str) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        return self._client.delete(memory_id)

    async def ping(self) -> bool:
        return True
