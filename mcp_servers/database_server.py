from __future__ import annotations

import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from .base import MCPServer


class DatabaseMCPServer(MCPServer):
    """MCP server for tools_database — database query pipeline (query-lifecycle)."""

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="tools_database", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()
        self._connections: dict[str, sqlite3.Connection] = {}
        self._query_cache: dict[str, tuple[float, Any]] = {}

        self.register("open_connection", "Open a database connection",
                       self._s({"connection_string": "string", "connection_id?": "string",
                                "db_type?": "string"}), self.open_connection)
        self.register("analyze_schema", "Analyze database schema — tables, columns, indexes",
                       self._s({"connection_id": "string"}), self.analyze_schema)
        self.register("build_query", "Build a safe parameterized SQL query",
                       self._s({"table": "string", "columns?": "array", "where?": "object",
                                "order_by?": "string", "limit?": "int", "query_type?": "string"}),
                       self.build_query)
        self.register("execute_query", "Execute a SQL query with parameterized inputs",
                       self._s({"connection_id": "string", "query": "string",
                                "params?": "array", "timeout_ms?": "int"}),
                       self.execute_query)
        self.register("begin_transaction", "Begin a database transaction",
                       self._s({"connection_id": "string"}), self.begin_transaction)
        self.register("commit_transaction", "Commit current transaction",
                       self._s({"connection_id": "string"}), self.commit_transaction)
        self.register("rollback_transaction", "Rollback current transaction",
                       self._s({"connection_id": "string"}), self.rollback_transaction)
        self.register("map_result", "Map query result to typed objects",
                       self._s({"columns": "array", "rows": "array", "schema?": "object"}),
                       self.map_result)
        self.register("cache_query", "Cache query result for reuse",
                       self._s({"query": "string", "params_hash": "string", "result": "object",
                                "ttl_seconds?": "int"}), self.cache_query)
        self.register("analyze_error", "Analyze database error message",
                       self._s({"error_message": "string", "query?": "string"}), self.analyze_error)
        self.register("suggest_migration", "Suggest database migration based on schema diff",
                       self._s({"current_schema": "object", "target_schema": "object"}),
                       self.suggest_migration)
        self.register("close_connection", "Close a database connection",
                       self._s({"connection_id": "string"}), self.close_connection)

    async def open_connection(self, connection_string: str, connection_id: str = "",
                              db_type: str = "sqlite") -> dict[str, Any]:
        cid = connection_id or f"db_{int(time.time() * 1000)}"
        try:
            if db_type == "sqlite":
                conn = sqlite3.connect(connection_string)
            else:
                return {"error": f"Unsupported db_type: {db_type}. Use sqlite for now."}
            self._connections[cid] = conn
            return {"connection_id": cid, "db_type": db_type, "connected": True,
                    "connection_string": connection_string}
        except Exception as e:
            return {"error": str(e), "connected": False}

    async def analyze_schema(self, connection_id: str) -> dict[str, Any]:
        conn = self._connections.get(connection_id)
        if not conn:
            return {"error": f"Connection not found: {connection_id}"}

        tables: list[dict[str, Any]] = []
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            for (table_name,) in cursor:
                cols = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
                columns = [{"name": c[1], "type": c[2], "nullable": not c[3],
                            "default": c[4], "pk": bool(c[5])} for c in cols]
                indexes = conn.execute(f"PRAGMA index_list('{table_name}')").fetchall()
                tables.append({"name": table_name, "columns": columns,
                               "column_count": len(columns), "indexes": [i[1] for i in indexes]})
        except Exception as e:
            return {"error": str(e)}
        return {"connection_id": connection_id, "tables": tables, "table_count": len(tables)}

    async def build_query(self, table: str, columns: list[str] | None = None,
                          where: dict[str, Any] | None = None,
                          order_by: str = "", limit: int = 100,
                          query_type: str = "SELECT") -> dict[str, Any]:
        cols = ", ".join(columns) if columns else "*"
        query_parts = [f"{query_type} {cols} FROM {table}"]

        params: list[Any] = []
        if where:
            conditions = []
            for col, val in where.items():
                conditions.append(f"{col} = ?")
                params.append(val)
            query_parts.append("WHERE " + " AND ".join(conditions))

        if order_by:
            query_parts.append(f"ORDER BY {order_by}")
        if limit:
            query_parts.append(f"LIMIT {limit}")

        query = " ".join(query_parts)
        return {"query": query, "params": params, "param_count": len(params), "table": table}

    async def execute_query(self, connection_id: str, query: str,
                            params: list[Any] | None = None,
                            timeout_ms: int = 30000) -> dict[str, Any]:
        conn = self._connections.get(connection_id)
        if not conn:
            return {"error": f"Connection not found: {connection_id}"}

        cache_key = f"{query}:{str(params)}"
        cached = self._query_cache.get(cache_key)
        if cached and time.time() - cached[0] < 60:
            return {"connection_id": connection_id, "rows": cached[1], "cached": True}

        t0 = time.perf_counter()
        try:
            cursor = conn.execute(query, params or [])
            if query.strip().upper().startswith("SELECT"):
                columns = [d[0] for d in cursor.description] if cursor.description else []
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            else:
                conn.commit()
                columns, rows = [], [{"affected_rows": cursor.rowcount}]

            latency = (time.perf_counter() - t0) * 1000
            result = {"connection_id": connection_id, "columns": columns, "rows": rows,
                      "row_count": len(rows), "latency_ms": latency, "cached": False}
            self._query_cache[cache_key] = (time.time(), rows)
            return result
        except Exception as e:
            return {"error": str(e), "query": query[:200]}

    async def begin_transaction(self, connection_id: str) -> dict[str, Any]:
        conn = self._connections.get(connection_id)
        if not conn:
            return {"error": f"Connection not found: {connection_id}"}
        conn.execute("BEGIN")
        return {"connection_id": connection_id, "transaction": "started"}

    async def commit_transaction(self, connection_id: str) -> dict[str, Any]:
        conn = self._connections.get(connection_id)
        if not conn:
            return {"error": f"Connection not found: {connection_id}"}
        conn.commit()
        return {"connection_id": connection_id, "transaction": "committed"}

    async def rollback_transaction(self, connection_id: str) -> dict[str, Any]:
        conn = self._connections.get(connection_id)
        if not conn:
            return {"error": f"Connection not found: {connection_id}"}
        conn.rollback()
        return {"connection_id": connection_id, "transaction": "rolled_back"}

    async def map_result(self, columns: list[str], rows: list[dict[str, Any]],
                         schema: dict[str, Any] | None = None) -> dict[str, Any]:
        type_guesses: dict[str, str] = {}
        if rows and columns:
            for col in columns:
                sample_values = [r.get(col) for r in rows[:10] if r.get(col) is not None]
                if not sample_values:
                    type_guesses[col] = "unknown"
                elif all(isinstance(v, int) for v in sample_values):
                    type_guesses[col] = "int"
                elif all(isinstance(v, float) for v in sample_values):
                    type_guesses[col] = "float"
                elif all(isinstance(v, str) for v in sample_values):
                    type_guesses[col] = "str"
                else:
                    type_guesses[col] = "mixed"
        return {"columns": columns, "type_guesses": type_guesses, "row_count": len(rows)}

    async def cache_query(self, query: str, params_hash: str, result: dict[str, Any],
                          ttl_seconds: int = 300) -> dict[str, Any]:
        key = f"{query}:{params_hash}"
        self._query_cache[key] = (time.time(), result.get("rows", []))
        return {"cached": True, "ttl_seconds": ttl_seconds, "key": key[:100]}

    async def analyze_error(self, error_message: str, query: str = "") -> dict[str, Any]:
        analysis = {"error": error_message, "issues": [], "fix": ""}
        err_lower = error_message.lower()
        if "no such table" in err_lower:
            analysis = {**analysis, "issues": ["missing_table"],
                        "fix": "Check table name spelling or run migration to create it"}
        elif "syntax error" in err_lower:
            analysis = {**analysis, "issues": ["sql_syntax"],
                        "fix": "Check SQL syntax — missing comma, quote, or keyword"}
        elif "unique constraint" in err_lower.lower() or "UNIQUE" in error_message:
            analysis = {**analysis, "issues": ["duplicate_key"],
                        "fix": "Value already exists. Use INSERT OR REPLACE or check for existing row"}
        elif "foreign key" in err_lower.lower():
            analysis = {**analysis, "issues": ["foreign_key_violation"],
                        "fix": "Referenced row does not exist. Insert the parent row first"}
        elif "database is locked" in err_lower:
            analysis = {**analysis, "issues": ["locked"],
                        "fix": "Database is locked by another process. Wait and retry"}
        return analysis

    async def suggest_migration(self, current_schema: dict[str, Any],
                                target_schema: dict[str, Any]) -> dict[str, Any]:
        current_tables = {t["name"] for t in current_schema.get("tables", [])}
        target_tables = {t["name"] for t in target_schema.get("tables", [])}

        migration_sql: list[str] = []
        for table in target_tables - current_tables:
            migration_sql.append(f"CREATE TABLE {table} (...); -- New table")

        for table in current_tables - target_tables:
            migration_sql.append(f"DROP TABLE IF EXISTS {table}; -- Removed table")

        for table in current_tables & target_tables:
            cur_cols = {c["name"] for c in current_schema["tables"] if c["name"] == table}
            migration_sql.append(f"-- ALTER TABLE {table} ...; -- Schema changed")

        return {"migration_sql": migration_sql, "steps": len(migration_sql)}

    async def close_connection(self, connection_id: str) -> dict[str, Any]:
        conn = self._connections.pop(connection_id, None)
        if conn:
            conn.close()
            return {"connection_id": connection_id, "closed": True}
        return {"error": f"Connection not found: {connection_id}"}

    @staticmethod
    def _s(props: dict[str, str]) -> dict[str, Any]:
        required = [k for k in props if not k.endswith("?")]
        properties = {}
        for k, v in props.items():
            name = k.rstrip("?")
            type_map = {"string": "string", "int": "integer", "bool": "boolean", "float": "number", "array": "array", "object": "object"}
            properties[name] = {"type": type_map.get(v, "string"), "description": f"The {name} parameter"}
        return {"type": "object", "properties": properties, "required": required}
