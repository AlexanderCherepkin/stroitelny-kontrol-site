from __future__ import annotations

import asyncio
import json
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]


@dataclass
class MCPToolResult:
    content: list[dict[str, Any]]
    is_error: bool = False


class MCPServer:
    """Base MCP server implementing JSON-RPC protocol over stdio."""

    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version
        self._tools: dict[str, MCPTool] = {}
        self._initialized = False

    def register_tool(self, tool: MCPTool):
        self._tools[tool.name] = tool

    def register(self, name: str, description: str, input_schema: dict[str, Any],
                 handler: Callable[..., Any]):
        self._tools[name] = MCPTool(name=name, description=description,
                                     input_schema=input_schema, handler=handler)

    async def run_stdio(self):
        """Run server over stdio (JSON-RPC)."""
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        writer_transport, writer_protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout.buffer
        )
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, loop)

        buffer = ""
        while True:
            try:
                line = await reader.readline()
                if not line:
                    break
                line_text = line.decode("utf-8").strip()
                if not line_text:
                    continue

                request = json.loads(line_text)
                response = await self._handle_request(request)
                if response is not None:
                    writer.write((json.dumps(response) + "\n").encode("utf-8"))
                    await writer.drain()
            except json.JSONDecodeError:
                continue
            except Exception:
                error_response = self._error_response(None, -32603, traceback.format_exc())
                writer.write((json.dumps(error_response) + "\n").encode("utf-8"))
                try:
                    await writer.drain()
                except Exception:
                    pass

    async def ping(self) -> bool:
        """Health check: return True if server is responsive.

        Servers that register tools during construction are considered healthy
        even before an explicit initialize handshake (e.g. direct registry use).
        """
        return self._initialized or bool(self._tools)

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> MCPToolResult:
        tool = self._tools.get(tool_name)
        if not tool:
            return MCPToolResult(content=[{"type": "text", "text": f"Tool not found: {tool_name}"}],
                                 is_error=True)
        try:
            result = tool.handler(**arguments)
            if asyncio.iscoroutine(result):
                result = await result
            return MCPToolResult(content=[{"type": "text", "text": json.dumps(result, ensure_ascii=False)}])
        except Exception as e:
            return MCPToolResult(content=[{"type": "text", "text": f"Error: {e}\n{traceback.format_exc()}"}],
                                 is_error=True)

    def get_tools_list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.input_schema,
            }
            for t in self._tools.values()
        ]

    async def _handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method", "")
        req_id = request.get("id")

        if method == "initialize":
            self._initialized = True
            return self._success_response(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": self.name, "version": self.version},
            })

        if method == "notifications/initialized":
            return None

        if method == "tools/list":
            return self._success_response(req_id, {"tools": self.get_tools_list()})

        if method == "tools/call":
            params = request.get("params", {})
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = await self.call_tool(tool_name, arguments)
            return self._success_response(req_id, {
                "content": result.content,
                "isError": result.is_error,
            })

        return self._error_response(req_id, -32601, f"Method not found: {method}")

    def _success_response(self, req_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _error_response(self, req_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
