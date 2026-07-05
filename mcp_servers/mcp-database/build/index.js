#!/usr/bin/env node
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema, } from "@modelcontextprotocol/sdk/types.js";
import { DatabaseSync } from "node:sqlite";
import fs from "fs/promises";
import path from "path";
const BASE_DIR = process.env.MCP_BASE_DIR || process.cwd();
const DB_DIR = path.join(BASE_DIR, ".mcp_databases");
function resolveDbPath(name) {
    const safeName = name.replace(/[^a-zA-Z0-9_-]/g, "_");
    const resolved = path.resolve(DB_DIR, `${safeName}.db`);
    const normalizedBase = path.normalize(DB_DIR);
    const normalizedTarget = path.normalize(resolved);
    if (!normalizedTarget.startsWith(normalizedBase)) {
        throw new Error(`Invalid database name: ${name}`);
    }
    return resolved;
}
async function ensureDbDir() {
    try {
        await fs.mkdir(DB_DIR, { recursive: true });
    }
    catch {
        // ignore
    }
}
// In-memory connection cache
const connections = new Map();
function getConnection(dbName) {
    if (connections.has(dbName)) {
        return connections.get(dbName);
    }
    const dbPath = resolveDbPath(dbName);
    const db = new DatabaseSync(dbPath);
    connections.set(dbName, db);
    return db;
}
const QUERY_TOOL = {
    name: "query",
    description: "Execute a SQL query on a SQLite database. " +
        "SELECT returns rows; INSERT/UPDATE/DELETE returns affected count.",
    inputSchema: {
        type: "object",
        properties: {
            database: {
                type: "string",
                description: "Database name (filename without extension)",
            },
            sql: {
                type: "string",
                description: "SQL query to execute",
            },
            params: {
                type: "array",
                description: "Query parameters",
                items: {},
            },
        },
        required: ["database", "sql"],
    },
};
const EXECUTE_TOOL = {
    name: "execute",
    description: "Execute a non-SELECT SQL statement (INSERT, UPDATE, DELETE, CREATE, DROP, ALTER). " +
        "Returns number of rows affected.",
    inputSchema: {
        type: "object",
        properties: {
            database: {
                type: "string",
                description: "Database name (filename without extension)",
            },
            sql: {
                type: "string",
                description: "SQL statement to execute",
            },
            params: {
                type: "array",
                description: "Statement parameters",
                items: {},
            },
        },
        required: ["database", "sql"],
    },
};
const TRANSACTION_TOOL = {
    name: "transaction",
    description: "Execute multiple SQL statements in a single transaction. " +
        "All succeed or all roll back on failure.",
    inputSchema: {
        type: "object",
        properties: {
            database: {
                type: "string",
                description: "Database name",
            },
            statements: {
                type: "array",
                description: "Array of SQL statements",
                items: {
                    type: "object",
                    properties: {
                        sql: { type: "string" },
                        params: { type: "array", items: {}, default: [] },
                    },
                    required: ["sql"],
                },
            },
        },
        required: ["database", "statements"],
    },
};
const LIST_TABLES_TOOL = {
    name: "list_tables",
    description: "List all tables in a database",
    inputSchema: {
        type: "object",
        properties: {
            database: {
                type: "string",
                description: "Database name",
            },
        },
        required: ["database"],
    },
};
const TOOLS = [QUERY_TOOL, EXECUTE_TOOL, TRANSACTION_TOOL, LIST_TABLES_TOOL];
async function handleQuery(args) {
    await ensureDbDir();
    const dbName = String(args.database);
    const sql = String(args.sql).trim();
    const params = args.params || [];
    if (!sql.toLowerCase().startsWith("select")) {
        throw new Error("Use 'execute' tool for non-SELECT statements");
    }
    const db = getConnection(dbName);
    const stmt = db.prepare(sql);
    const rows = stmt.all(...params);
    return {
        content: [
            {
                type: "text",
                text: JSON.stringify({ rows }, null, 2),
            },
        ],
    };
}
async function handleExecute(args) {
    await ensureDbDir();
    const dbName = String(args.database);
    const sql = String(args.sql).trim();
    const params = args.params || [];
    if (sql.toLowerCase().startsWith("select")) {
        throw new Error("Use 'query' tool for SELECT statements");
    }
    const db = getConnection(dbName);
    const stmt = db.prepare(sql);
    const result = stmt.run(...params);
    return {
        content: [
            {
                type: "text",
                text: JSON.stringify({
                    changes: result.changes,
                    lastInsertRowid: Number(result.lastInsertRowid),
                }, null, 2),
            },
        ],
    };
}
async function handleTransaction(args) {
    await ensureDbDir();
    const dbName = String(args.database);
    const statements = args.statements || [];
    if (statements.length === 0) {
        throw new Error("No statements provided");
    }
    const db = getConnection(dbName);
    // SQLite transaction
    db.exec("BEGIN TRANSACTION");
    const results = [];
    try {
        for (const { sql, params = [] } of statements) {
            const trimmed = sql.trim();
            const stmt = db.prepare(trimmed);
            if (trimmed.toLowerCase().startsWith("select")) {
                const rows = stmt.all(...params);
                results.push({ sql: trimmed, rows });
            }
            else {
                const result = stmt.run(...params);
                results.push({
                    sql: trimmed,
                    changes: result.changes,
                    lastInsertRowid: Number(result.lastInsertRowid),
                });
            }
        }
        db.exec("COMMIT");
    }
    catch (err) {
        db.exec("ROLLBACK");
        throw new Error(`Transaction failed: ${err.message}`);
    }
    return {
        content: [
            {
                type: "text",
                text: JSON.stringify({ status: "committed", results }, null, 2),
            },
        ],
    };
}
async function handleListTables(args) {
    await ensureDbDir();
    const dbName = String(args.database);
    const db = getConnection(dbName);
    const stmt = db.prepare("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name");
    const rows = stmt.all();
    return {
        content: [
            {
                type: "text",
                text: JSON.stringify({ tables: rows.map((r) => r.name) }, null, 2),
            },
        ],
    };
}
const server = new Server({ name: "mcp-database", version: "1.0.0" }, { capabilities: { tools: {} } });
server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));
server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;
    switch (name) {
        case "query":
            return handleQuery(args || {});
        case "execute":
            return handleExecute(args || {});
        case "transaction":
            return handleTransaction(args || {});
        case "list_tables":
            return handleListTables(args || {});
        default:
            throw new Error(`Unknown tool: ${name}`);
    }
});
async function main() {
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error("mcp-database server running on stdio");
    console.error(`Database directory: ${DB_DIR}`);
}
main().catch((error) => {
    console.error("Fatal error:", error);
    process.exit(1);
});
//# sourceMappingURL=index.js.map