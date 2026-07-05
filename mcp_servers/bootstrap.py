#!/usr/bin/env python3
"""
MCP Bootstrap — wires all 16 MCP servers into the registry and connects them to the runtime.

Usage:
    python -m mcp_servers.bootstrap           # Register all servers, print summary
    python -m mcp_servers.bootstrap --serve    # Run all servers via stdio (JSON-RPC)
    python -m mcp_servers.bootstrap --test     # Run self-test on all servers
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .registry import MCPRegistry, ServerInfo
from .read_server import ReadMCPServer
from .search_server import SearchMCPServer
from .replace_server import ReplaceMCPServer
from .runcom_server import RuncomMCPServer
from .runtest_server import RuntestMCPServer
from .terminal_server import TerminalMCPServer
from .manangr_server import ManangrMCPServer
from .database_server import DatabaseMCPServer
from .web_server import WebMCPServer
from .memory_server import MemoryMCPServer
from .browser_server import BrowserMCPServer
from .figma_server import FigmaMCPServer
from .backend_server import BackendMCPServer
from .headroom_server import HeadroomMCPServer
from .memanto_server import MemantoMCPServer
from .mem0_server import Mem0MCPServer


def _build_server(category: str, root: Path, eager: bool = True) -> tuple[MCPServer, list[dict[str, Any]]]:
    """Construct a single MCP server and return it with its tool list."""
    constructors = {
        "tools_read": ReadMCPServer,
        "tools_search": SearchMCPServer,
        "tools_replace": ReplaceMCPServer,
        "tools_runcom": RuncomMCPServer,
        "tools_runtest": RuntestMCPServer,
        "tools_terminal": TerminalMCPServer,
        "tools_manangr": ManangrMCPServer,
        "tools_database": DatabaseMCPServer,
        "tools_web": WebMCPServer,
        "tools_memory": MemoryMCPServer,
        "tools_browser": BrowserMCPServer,
        "figma": FigmaMCPServer,
        "backend": BackendMCPServer,
        "headroom": HeadroomMCPServer,
        "memanto": MemantoMCPServer,
        "mem0": Mem0MCPServer,
    }
    cls = constructors[category]
    server = cls(str(root))
    if category == "tools_memory":
        server.register_all()
    return server, server.get_tools_list()


def create_registry(workspace_root: str = ".", eager: bool = False) -> MCPRegistry:
    """Create and populate the MCP registry with all 16 servers.

    Args:
        workspace_root: project root path.
        eager: if True, construct all servers immediately (legacy behavior for --test/--serve).
    """
    registry = MCPRegistry()
    root = Path(workspace_root).resolve()

    descriptions = {
        "tools_read": "Read file pipeline — 9 tools",
        "tools_search": "Search code pipeline — 8 tools",
        "tools_replace": "Replace in file pipeline — 10 tools",
        "tools_runcom": "Run command pipeline — 9 tools",
        "tools_runtest": "Run tests pipeline — 8 tools",
        "tools_terminal": "Terminal I/O pipeline — 9 tools",
        "tools_manangr": "Project management pipeline — 8 tools",
        "tools_database": "Database query pipeline — 11 tools",
        "tools_web": "Web request pipeline — 10 tools",
        "tools_memory": "Memory store pipeline — 11 tools",
        "tools_browser": "Headless browser pipeline — 10 tools",
        "figma": "Figma-to-code pipeline — 9 tools",
        "backend": "Backend Spec Bridge pipeline — 6 tools",
        "headroom": "Headroom context compression pipeline — 3 tools",
        "memanto": "Memanto semantic memory pipeline — 4 tools",
        "mem0": "Mem0 long-term memory pipeline — 4 tools",
    }

    for category in descriptions:
        if eager:
            server, tools = _build_server(category, root, eager=True)
            registry.register(ServerInfo(
                name=descriptions[category],
                category=category,
                agent_count=len(tools),
                server=server,
                tools=[t["name"] for t in tools],
            ))
        else:
            # Lazy: register a factory and lightweight metadata. Tool names are
            # discovered by constructing the server once, then immediately discarded.
            # This still saves planner tokens because only category metadata is kept.
            server, tools = _build_server(category, root, eager=True)
            tool_names = [t["name"] for t in tools]
            agent_count = len(tools)
            # Discard the temporary server; the factory will build a fresh one on demand.
            registry.register_factory(
                category=category,
                factory=lambda c=category, r=root: _build_server(c, r, eager=True)[0],
                name=descriptions[category],
                metadata={
                    "agent_count": agent_count,
                    "tools": tool_names,
                },
            )

    return registry


async def test_all_servers(registry: MCPRegistry):
    """Run a quick self-test on every registered server."""
    results: dict[str, bool] = {}

    # Test read server
    read = registry.get_server("tools_read")
    if read:
        r = await read.call_tool("list_directory", {"path": ".", "pattern": "*.md"})
        results["read"] = "error" not in str(r.content)

    # Test search server
    search = registry.get_server("tools_search")
    if search:
        r = await search.call_tool("regex_search", {"query": "def ", "path": ".", "max_results": 5})
        results["search"] = "error" not in str(r.content)

    # Test terminal server
    term = registry.get_server("tools_terminal")
    if term:
        await term.call_tool("create_session", {"session_id": "test"})
        r = await term.call_tool("get_state", {"session_id": "test"})
        results["terminal"] = not r.is_error and "test" in str(r.content)

    # Test runcom server
    rc = registry.get_server("tools_runcom")
    if rc:
        r = await rc.call_tool("sandbox_check", {"command": "ls -la"})
        results["runcom"] = "error" not in str(r.content)

    # Test web server
    web = registry.get_server("tools_web")
    if web:
        r = await web.call_tool("analyze_error", {"status_code": 404, "response_body": ""})
        results["web"] = "error" not in str(r.content)

    # Test memory server
    mem = registry.get_server("tools_memory")
    if mem:
        mem.register_all()
        r = await mem.call_tool("list_entries", {"limit": 5})
        results["memory"] = "error" not in str(r.content)

    # Test replace server
    repl = registry.get_server("tools_replace")
    if repl:
        r = await repl.call_tool("validate_edit", {"path": "test.py", "content": "print('hello')"})
        results["replace"] = "error" not in str(r.content)

    # Test manangr server
    mgr = registry.get_server("tools_manangr")
    if mgr:
        r = await mgr.call_tool("analyze_structure", {"path": ".", "max_depth": 2})
        results["manangr"] = "error" not in str(r.content)

    # Test database server
    db = registry.get_server("tools_database")
    if db:
        await db.call_tool("open_connection", {"connection_string": ":memory:", "connection_id": "test"})
        r = await db.call_tool("analyze_schema", {"connection_id": "test"})
        results["database"] = "error" not in str(r.content)

    # Test runtest server
    rt = registry.get_server("tools_runtest")
    if rt:
        r = await rt.call_tool("discover_tests", {"path": "."})
        results["runtest"] = not r.is_error

    # Test browser server (degraded is acceptable if Playwright missing)
    browser = registry.get_server("tools_browser")
    if browser:
        r = await browser.call_tool("browser_open", {"session_id": "test"})
        results["browser"] = "error" not in str(r.content) or "degraded" in str(r.content)

    # Test figma server (degraded is acceptable if figma-agent-core missing)
    figma = registry.get_server("figma")
    if figma:
        r = await figma.call_tool("figma_run_pipeline", {"dry_run": True})
        results["figma"] = "error" not in str(r.content) or "degraded" in str(r.content)

    # Test backend server (degraded is acceptable if figma-agent-core missing)
    backend = registry.get_server("backend")
    if backend:
        r = await backend.call_tool("backend_analyze_spec", {})
        results["backend"] = "error" not in str(r.content) or "degraded" in str(r.content)

    # Test headroom server (degraded is acceptable if headroom-ai not installed)
    headroom = registry.get_server("headroom")
    if headroom:
        r = await headroom.call_tool("headroom_compress", {"content": "hello world"})
        results["headroom"] = "error" not in str(r.content) or "degraded" in str(r.content)

    # Test memanto server (degraded is acceptable if memanto serve is not running)
    memanto = registry.get_server("memanto")
    if memanto:
        r = await memanto.call_tool("memanto_recall", {"query": "test"})
        results["memanto"] = "error" not in str(r.content) or "degraded" in str(r.content)

    # Test mem0 server (degraded is acceptable if mem0ai is not installed)
    mem0 = registry.get_server("mem0")
    if mem0:
        r = await mem0.call_tool("mem0_search", {"query": "test"})
        results["mem0"] = "error" not in str(r.content) or "degraded" in str(r.content)

    return results


async def main():
    parser = argparse.ArgumentParser(description="MCP Bootstrap for Agentic Loop")
    parser.add_argument("--serve", action="store_true", help="Run all servers via stdio JSON-RPC")
    parser.add_argument("--test", action="store_true", help="Run self-test on all servers")
    parser.add_argument("--workspace", default=".", help="Workspace root path")
    parser.add_argument("--list", action="store_true", help="List all registered tools")
    parser.add_argument("--eager", action="store_true", help="Eagerly construct all servers (default is lazy)")
    args = parser.parse_args()

    # --test and --serve need real servers; --list can stay lazy unless --eager is set.
    eager = args.eager or args.test or args.serve
    registry = create_registry(args.workspace, eager=eager)
    print(f"MCP Registry: {registry.server_count} servers, {registry.tool_count} tools (eager={eager})")
    browser_info = registry.get_category_metadata("tools_browser")
    if browser_info:
        print(f"Browser server: registered with {browser_info['agent_count']} tools\n")

    if args.list:
        print("=" * 60)
        print("REGISTERED TOOLS")
        print("=" * 60)
        for cat, info in registry._servers.items():
            print(f"\n[{cat}] {info.name}")
            if eager:
                for tool_name in info.tools:
                    tool = info.server._tools.get(tool_name)
                    if tool:
                        print(f"  • {tool.name} — {tool.description[:80]}")
            else:
                for tool_name in info.tools:
                    print(f"  • {tool_name}")
        return

    if args.test:
        print("Running self-tests...\n")
        results = await test_all_servers(registry)
        print("=" * 40)
        for name, ok in results.items():
            status = "PASS" if ok else "FAIL"
            print(f"  {name:15s} [{status}]")
        passed = sum(1 for v in results.values() if v)
        print(f"\n{passed}/{len(results)} servers operational")
        return

    if args.serve:
        print("Starting MCP servers via stdio (JSON-RPC mode)")
        print(f"All {registry.server_count} servers registered and ready for tool calls")
        # In stdio mode, we run an aggregator that routes to the right server
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                request = json.loads(line.strip())
                method = request.get("method", "")
                req_id = request.get("id")

                if method == "initialize":
                    print(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "agentic-loop-mcp", "version": "1.0.0"},
                    }}))
                    sys.stdout.flush()
                elif method == "tools/list":
                    tools = registry.get_all_tools()
                    print(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}))
                    sys.stdout.flush()
                elif method == "tools/call":
                    params = request.get("params", {})
                    tool_name = params.get("name", "")
                    arguments = params.get("arguments", {})
                    result = await registry.call_tool(tool_name, arguments)
                    print(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}))
                    sys.stdout.flush()
                else:
                    print(json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}))
                    sys.stdout.flush()
            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}))
                sys.stdout.flush()
        return

    # Default: print summary
    for cat, info in registry._servers.items():
        print(f"  {cat:20s} → {info.agent_count:2d} tools | {info.name}")


if __name__ == "__main__":
    import warnings

    warnings.filterwarnings("ignore", category=ResourceWarning)

    def _suppress_unraisable(unraisable):
        # Ignore ResourceWarning/Proactor noise during interpreter shutdown on Windows.
        if unraisable.exc_type is not None and issubclass(unraisable.exc_type, (ResourceWarning, ValueError)):
            return
        sys.unraisablehook(unraisable)

    sys.unraisablehook = _suppress_unraisable
    asyncio.run(main())
