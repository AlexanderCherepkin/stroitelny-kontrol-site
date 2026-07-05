from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .base import MCPServer, MCPTool


@dataclass
class ServerInfo:
    name: str
    category: str
    agent_count: int
    server: MCPServer | None
    tools: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    _factory: Callable[[], MCPServer] | None = None

    def ensure_loaded(self) -> MCPServer | None:
        if self.server is None and self._factory is not None:
            self.server = self._factory()
            self._factory = None
        return self.server


class MCPRegistry:
    """Registry and discovery for all MCP servers across tools_* categories.

    Supports both eager registration (legacy ServerInfo with a live server)
    and lazy registration (factory that constructs the server on first use).
    """

    CATEGORY_MAP = {
        "tools_read": "Read file pipeline",
        "tools_search": "Search code pipeline",
        "tools_replace": "Replace in file pipeline",
        "tools_runcom": "Run command pipeline",
        "tools_runtest": "Run tests pipeline",
        "tools_terminal": "Terminal I/O pipeline",
        "tools_manangr": "Project management pipeline",
        "tools_database": "Database query pipeline",
        "tools_web": "Web request pipeline",
        "tools_memory": "Memory store pipeline",
        "tools_browser": "Headless browser pipeline",
        "figma": "Figma-to-code pipeline",
        "backend": "Backend Spec Bridge pipeline",
        "headroom": "Headroom context compression pipeline",
        "memanto": "Memanto semantic memory pipeline",
        "mem0": "Mem0 long-term memory pipeline",
    }

    def __init__(self):
        self._servers: dict[str, ServerInfo] = {}
        self._tool_to_server: dict[str, str] = {}

    def register(self, info: ServerInfo):
        """Eager registration: server is already constructed."""
        self._servers[info.category] = info
        for tool_name in info.tools:
            self._tool_to_server[tool_name] = info.category

    def register_factory(
        self,
        category: str,
        factory: Callable[[], MCPServer],
        name: str,
        metadata: dict[str, Any] | None = None,
    ):
        """Lazy registration: server is constructed only on first access."""
        info = ServerInfo(
            name=name,
            category=category,
            agent_count=metadata.get("agent_count", 0) if metadata else 0,
            server=None,
            tools=metadata.get("tools", []) if metadata else [],
            metadata=metadata or {},
            _factory=factory,
        )
        self._servers[category] = info
        for tool_name in info.tools:
            self._tool_to_server[tool_name] = category

    def _ensure_loaded(self, category: str) -> ServerInfo | None:
        info = self._servers.get(category)
        if not info:
            return None
        info.ensure_loaded()
        return info

    def get_server(self, category: str) -> MCPServer | None:
        info = self._ensure_loaded(category)
        return info.server if info else None

    def get_category_metadata(self, category: str) -> dict[str, Any] | None:
        info = self._servers.get(category)
        if not info:
            return None
        return {
            "name": info.name,
            "category": info.category,
            "agent_count": info.agent_count,
            "tools": info.tools,
            "metadata": info.metadata,
        }

    def get_all_servers(self) -> dict[str, MCPServer]:
        return {cat: info.ensure_loaded() for cat, info in self._servers.items() if info.ensure_loaded()}

    def get_all_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for info in self._servers.values():
            server = info.ensure_loaded()
            if server:
                tools.extend(server.get_tools_list())
        return tools

    def find_tool(self, tool_name: str) -> MCPServer | None:
        category = self._tool_to_server.get(tool_name)
        if not category:
            return None
        info = self._ensure_loaded(category)
        return info.server if info else None

    async def ping(self, category: str | None = None) -> dict[str, bool]:
        """Health check one or all servers. Returns {name: bool}."""
        results: dict[str, bool] = {}
        if category:
            info = self._ensure_loaded(category)
            if info and info.server:
                results[info.name] = await info.server.ping()
        else:
            for info in self._servers.values():
                server = info.ensure_loaded()
                if server:
                    results[info.name] = await server.ping()
        return results

    def is_healthy(self, tool_name: str) -> bool:
        """Quick check if the server owning a tool is healthy."""
        server = self.find_tool(tool_name)
        if not server:
            return False
        return server._initialized

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        server = self.find_tool(tool_name)
        if not server:
            return {"error": f"Tool not found: {tool_name}", "is_error": True}
        if not await server.ping():
            return {"error": f"MCP server for {tool_name} is not responding", "is_error": True}
        result = await server.call_tool(tool_name, arguments)
        return {"content": result.content, "is_error": result.is_error}

    @property
    def server_count(self) -> int:
        return len(self._servers)

    @property
    def tool_count(self) -> int:
        return len(self._tool_to_server)

    def categories(self) -> list[str]:
        return list(self._servers.keys())
