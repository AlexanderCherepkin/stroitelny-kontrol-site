# Community 27

> 24 nodes

## Key Concepts

- **MCPServer** (54 connections) — `mcp_servers/base.py`
- **ServerInfo** (20 connections) — `mcp_servers/registry.py`
- **MCPTool** (10 connections) — `mcp_servers/base.py`
- **registry.py** (9 connections) — `mcp_servers/registry.py`
- **._handle_request()** (7 connections) — `mcp_servers/base.py`
- **.call_tool()** (6 connections) — `mcp_servers/base.py`
- **Any** (6 connections) — `mcp_servers/base.py`
- **MCP Servers Package Init — Exports MCPServer, MCPTool, MCPRegistry, ServerInfo** (5 connections) — `mcp_servers/__init__.py`
- **.run_stdio()** (5 connections) — `mcp_servers/base.py`
- **._error_response()** (4 connections) — `mcp_servers/base.py`
- **.test_registry_is_healthy()** (4 connections) — `runtime/test_resilience.py`
- **.get_tools_list()** (3 connections) — `mcp_servers/base.py`
- **.register()** (3 connections) — `mcp_servers/base.py`
- **._success_response()** (3 connections) — `mcp_servers/base.py`
- **.register()** (3 connections) — `mcp_servers/registry.py`
- **MCPServer._handle_request — JSON-RPC method router** (2 connections) — `mcp_servers/base.py`
- **.ping()** (2 connections) — `mcp_servers/base.py`
- **.register_tool()** (2 connections) — `mcp_servers/base.py`
- **.test_server_ping()** (2 connections) — `runtime/test_resilience.py`
- **.__init__()** (1 connections) — `mcp_servers/base.py`
- **Base MCP server implementing JSON-RPC protocol over stdio.** (1 connections) — `mcp_servers/base.py`
- **Run server over stdio (JSON-RPC).** (1 connections) — `mcp_servers/base.py`
- **Health check: return True if server is responsive.** (1 connections) — `mcp_servers/base.py`
- **Eager registration: server is already constructed.** (1 connections) — `mcp_servers/registry.py`

## Relationships

- [[Community 20]] (14 shared connections)
- [[Community 16]] (13 shared connections)
- [[Community 19]] (11 shared connections)
- [[Community 48]] (4 shared connections)
- [[Community 6]] (3 shared connections)
- [[Community 54]] (3 shared connections)
- [[Community 58]] (3 shared connections)
- [[Community 88]] (2 shared connections)
- [[Community 12]] (2 shared connections)
- [[Community 47]] (2 shared connections)
- [[Community 73]] (2 shared connections)
- [[Community 67]] (2 shared connections)

## Source Files

- `mcp_servers/__init__.py`
- `mcp_servers/base.py`
- `mcp_servers/registry.py`
- `runtime/test_resilience.py`

## Audit Trail

- EXTRACTED: 107 (69%)
- INFERRED: 48 (31%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*