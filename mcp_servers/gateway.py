from __future__ import annotations

from typing import Any

from .registry import MCPRegistry


class MCPGateway:
    """Lazy gateway in front of MCPRegistry.

    The gateway exposes category-level metadata to the planner without forcing
    every MCP server to be constructed. Servers are materialized only when a tool
    in their category is actually invoked. This keeps the planner context small
    and saves initialization time and tokens.
    """

    def __init__(self, registry: MCPRegistry):
        self._registry = registry

    @property
    def is_available(self) -> bool:
        return self._registry is not None

    def categories(self) -> list[str]:
        """Return registered category names without loading any server."""
        if not self._registry:
            return []
        return self._registry.categories()

    def category_metadata(self, category: str) -> dict[str, Any] | None:
        """Return lightweight metadata for a category without materializing it."""
        if not self._registry:
            return None
        return self._registry.get_category_metadata(category)

    def tools_for_category(self, category: str) -> list[dict[str, Any]]:
        """Return full tool descriptors for a category; loads the server if needed."""
        if not self._registry:
            return []
        server = self._registry.get_server(category)
        if not server:
            return []
        return server.get_tools_list()

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a single MCP tool, loading its server on demand."""
        if not self._registry:
            return {"error": "MCP not available", "is_error": True}
        return await self._registry.call_tool(tool_name, arguments)

    async def ping(self, category: str | None = None) -> dict[str, bool]:
        """Health-check one or all categories; loads servers as needed."""
        if not self._registry:
            return {}
        return await self._registry.ping(category)
