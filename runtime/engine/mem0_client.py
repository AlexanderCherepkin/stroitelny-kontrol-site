from __future__ import annotations

import importlib.util
import json
import os
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Mem0Config:
    """Runtime configuration for the optional Mem0 memory layer.

    Mem0 can be used either as an embedded Python library (local Chroma/Qdrant
    vector store + SQLite history) or via the managed cloud API. If neither is
    available, the client degrades gracefully and keeps memories in an
    in-memory fallback store so the ReAct loop continues.
    """

    enabled: bool = field(
        default_factory=lambda: os.getenv("MEM0_ENABLED", "true").lower()
        not in ("false", "0", "off", "no")
    )
    api_key: str | None = field(default_factory=lambda: os.getenv("MEM0_API_KEY") or None)
    host: str | None = field(default_factory=lambda: os.getenv("MEM0_HOST") or None)
    vector_store_provider: str = field(default_factory=lambda: os.getenv("MEM0_VECTOR_STORE", "chroma"))
    vector_store_path: str = field(default_factory=lambda: os.getenv("MEM0_VECTOR_STORE_PATH", "./memory_storage"))
    llm_provider: str = field(default_factory=lambda: os.getenv("MEM0_LLM_PROVIDER", "openai"))
    llm_model: str = field(default_factory=lambda: os.getenv("MEM0_LLM_MODEL", "gpt-4o-mini"))
    embedder_provider: str = field(default_factory=lambda: os.getenv("MEM0_EMBEDDER_PROVIDER", "openai"))
    user_id: str = field(default_factory=lambda: os.getenv("MEM0_USER_ID", "agentic_loop"))
    agent_id: str = field(default_factory=lambda: os.getenv("MEM0_AGENT_ID", "agentic_loop"))
    app_id: str | None = field(default_factory=lambda: os.getenv("MEM0_APP_ID") or None)
    run_id: str | None = field(default_factory=lambda: os.getenv("MEM0_RUN_ID") or None)
    custom_instructions: str | None = field(
        default_factory=lambda: os.getenv("MEM0_CUSTOM_INSTRUCTIONS") or None
    )


class Mem0Unavailable:
    """Sentinel returned when Mem0 SDK/API is not reachable."""

    pass


class Mem0Client:
    """Lightweight runtime client for the optional Mem0 memory layer.

    Mirrors the core Mem0 contract: add, search, get_all, delete. If the
    optional `mem0ai` package is not installed or the cloud API key is missing,
    the client falls back to an in-memory store so the agent system keeps
    working without external dependencies.
    """

    _instance: "Mem0Client | None" = None
    _lock = threading.Lock()

    def __new__(cls, config: Mem0Config | None = None) -> "Mem0Client":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, config: Mem0Config | None = None):
        if self._initialized:
            return
        self.config = config or Mem0Config()
        self._fallback_store: list[dict[str, Any]] = []
        self._mem0: Any = self._import_mem0()
        self._initialized = True

    @staticmethod
    def _import_mem0() -> Any:
        """Import optional mem0ai package if installed."""
        if importlib.util.find_spec("mem0") is None:
            return Mem0Unavailable()
        try:
            import mem0
            return mem0
        except Exception:
            return Mem0Unavailable()

    @property
    def is_available(self) -> bool:
        if not self.config.enabled:
            return False
        if isinstance(self._mem0, Mem0Unavailable):
            return False
        try:
            # For embedded mode (no API key), Memory construction is the real test.
            # For cloud mode, check the API key is present.
            if self.config.api_key:
                return bool(self.config.api_key)
            self._ensure_memory()
            return True
        except Exception:
            return False

    def _ensure_memory(self) -> Any:
        """Lazily construct the embedded Mem0 Memory instance."""
        if not hasattr(self, "_memory") or self._memory is None:
            from mem0 import Memory

            config = {
                "vector_store": {
                    "provider": self.config.vector_store_provider,
                    "config": {
                        "collection_name": "agent_memory_db",
                        "path": self.config.vector_store_path,
                    },
                },
                "llm": {
                    "provider": self.config.llm_provider,
                    "config": {"model": self.config.llm_model},
                },
                "embedder": {
                    "provider": self.config.embedder_provider,
                    "config": {},
                },
                "history_db_path": os.path.join(self.config.vector_store_path, "history.db"),
            }
            if self.config.custom_instructions:
                config["custom_instructions"] = self.config.custom_instructions
            self._memory = Memory.from_config(config)
        return self._memory

    def _entity_scope(self) -> dict[str, str]:
        scope: dict[str, str] = {}
        if self.config.user_id:
            scope["user_id"] = self.config.user_id
        if self.config.agent_id:
            scope["agent_id"] = self.config.agent_id
        if self.config.app_id:
            scope["app_id"] = self.config.app_id
        if self.config.run_id:
            scope["run_id"] = self.config.run_id
        return scope

    def _passthrough(self, operation: str, data: Any) -> dict[str, Any]:
        return {
            "available": False,
            "operation": operation,
            "result": data,
            "note": "Mem0 SDK/API unavailable; using in-memory fallback.",
        }

    def _fallback_add(self, messages: list[dict[str, str]], metadata: dict[str, Any] | None) -> dict[str, Any]:
        records = []
        for msg in messages:
            rec = {
                "id": f"fallback-{len(self._fallback_store)}",
                "memory": msg.get("content", ""),
                "role": msg.get("role", "user"),
                "metadata": metadata or {},
            }
            self._fallback_store.append(rec)
            records.append(rec)
        return {
            "available": False,
            "operation": "add",
            "results": records,
            "note": "Mem0 unavailable; memories kept in local fallback store.",
        }

    def _fallback_search(self, query: str, limit: int) -> dict[str, Any]:
        q = query.lower()
        matches = [
            {
                "id": rec.get("id"),
                "memory": rec.get("memory"),
                "score": 1.0,
                "metadata": rec.get("metadata"),
            }
            for rec in self._fallback_store
            if q in rec.get("memory", "").lower()
        ][:limit]
        return {
            "available": False,
            "operation": "search",
            "results": matches,
            "total_found": len(matches),
            "note": "Mem0 unavailable; searched in-memory fallback store.",
        }

    def _fallback_get_all(self, limit: int) -> dict[str, Any]:
        return {
            "available": False,
            "operation": "get_all",
            "results": self._fallback_store[-limit:],
            "total_found": len(self._fallback_store),
            "note": "Mem0 unavailable; listed in-memory fallback store.",
        }

    def add(
        self,
        messages: str | dict[str, str] | list[dict[str, str]],
        user_id: str | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        infer: bool = True,
    ) -> dict[str, Any]:
        """Store a memory (or a conversation turn) in Mem0. Falls back to in-memory store if Mem0 is down."""
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        elif isinstance(messages, dict):
            messages = [messages]

        if not self.is_available:
            return self._fallback_add(messages, metadata)

        try:
            filters = self._entity_scope()
            if user_id:
                filters["user_id"] = user_id
            if agent_id:
                filters["agent_id"] = agent_id
            if run_id:
                filters["run_id"] = run_id

            if self.config.api_key:
                from mem0 import MemoryClient

                client = MemoryClient(api_key=self.config.api_key, host=self.config.host or "https://api.mem0.ai")
                result = client.add(messages, filters=filters, metadata=metadata, infer=infer)
            else:
                result = self._ensure_memory().add(
                    messages,
                    filters=filters,
                    metadata=metadata,
                    infer=infer,
                )
            return {"available": True, "operation": "add", "result": result}
        except Exception as exc:
            return self._passthrough("add", {"error": str(exc)})

    def search(
        self,
        query: str,
        user_id: str | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
        limit: int = 5,
        threshold: float = 0.1,
    ) -> dict[str, Any]:
        """Retrieve relevant memories by semantic query. Falls back to substring search if Mem0 is down."""
        if not self.is_available:
            return self._fallback_search(query, limit)

        try:
            filters = self._entity_scope()
            if user_id:
                filters["user_id"] = user_id
            if agent_id:
                filters["agent_id"] = agent_id
            if run_id:
                filters["run_id"] = run_id

            if self.config.api_key:
                from mem0 import MemoryClient

                client = MemoryClient(api_key=self.config.api_key, host=self.config.host or "https://api.mem0.ai")
                result = client.search(query, filters=filters, top_k=limit, threshold=threshold)
            else:
                result = self._ensure_memory().search(query, filters=filters, top_k=limit, threshold=threshold)
            return {"available": True, "operation": "search", "result": result}
        except Exception as exc:
            return self._passthrough("search", {"error": str(exc)})

    def get_all(
        self,
        user_id: str | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List stored memories. Falls back to in-memory list if Mem0 is down."""
        if not self.is_available:
            return self._fallback_get_all(limit)

        try:
            filters = self._entity_scope()
            if user_id:
                filters["user_id"] = user_id
            if agent_id:
                filters["agent_id"] = agent_id
            if run_id:
                filters["run_id"] = run_id

            if self.config.api_key:
                from mem0 import MemoryClient

                client = MemoryClient(api_key=self.config.api_key, host=self.config.host or "https://api.mem0.ai")
                result = client.get_all(filters=filters, page_size=limit)
            else:
                result = self._ensure_memory().get_all(filters=filters, top_k=limit)
            return {"available": True, "operation": "get_all", "result": result}
        except Exception as exc:
            return self._passthrough("get_all", {"error": str(exc)})

    def delete(self, memory_id: str) -> dict[str, Any]:
        """Delete a memory by id. Falls back to no-op if Mem0 is down."""
        if not self.is_available:
            return {
                "available": False,
                "operation": "delete",
                "deleted": False,
                "note": "Mem0 unavailable; cannot delete from fallback store by id.",
            }

        try:
            if self.config.api_key:
                from mem0 import MemoryClient

                client = MemoryClient(api_key=self.config.api_key, host=self.config.host or "https://api.mem0.ai")
                client.delete(memory_id)
            else:
                self._ensure_memory().delete(memory_id)
            return {"available": True, "operation": "delete", "deleted": True}
        except Exception as exc:
            return self._passthrough("delete", {"error": str(exc), "deleted": False})

    def stats(self) -> dict[str, Any]:
        return {
            "available": self.is_available,
            "enabled": self.config.enabled,
            "mode": "cloud" if self.config.api_key else "embedded",
            "host": self.config.host,
            "user_id": self.config.user_id,
            "agent_id": self.config.agent_id,
            "fallback_entries": len(self._fallback_store),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.is_available,
            "enabled": self.config.enabled,
            "mode": "cloud" if self.config.api_key else "embedded",
            "host": self.config.host,
            "user_id": self.config.user_id,
            "agent_id": self.config.agent_id,
        }
