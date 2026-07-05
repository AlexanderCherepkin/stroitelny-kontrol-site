#!/usr/bin/env node
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema, } from "@modelcontextprotocol/sdk/types.js";
import fs from "fs/promises";
import path from "path";
const BASE_DIR = process.env.MCP_BASE_DIR || process.cwd();
const BACKUP_DIR = process.env.MCP_BACKUP_DIR || path.join(BASE_DIR, ".mcp_backups");
function resolvePath(targetPath) {
    const resolved = path.resolve(BASE_DIR, targetPath);
    const normalizedBase = path.normalize(BASE_DIR);
    const normalizedTarget = path.normalize(resolved);
    if (!normalizedTarget.startsWith(normalizedBase)) {
        throw new Error(`Access denied: path "${targetPath}" escapes the allowed base directory "${BASE_DIR}"`);
    }
    return resolved;
}
async function ensureBackupDir() {
    try {
        await fs.mkdir(BACKUP_DIR, { recursive: true });
    }
    catch {
        // ignore
    }
}
async function createBackup(filePath) {
    await ensureBackupDir();
    const timestamp = Date.now();
    const hash = Buffer.from(filePath).toString("base64url").slice(0, 16);
    const backupName = `${hash}_${timestamp}.bak`;
    const backupPath = path.join(BACKUP_DIR, backupName);
    const content = await fs.readFile(filePath);
    await fs.writeFile(backupPath, content);
    return backupPath;
}
const READ_FILE_TOOL = {
    name: "read_file",
    description: "Read the full contents of a file.",
    inputSchema: {
        type: "object",
        properties: {
            path: { type: "string", description: "Path to the file" },
            encoding: { type: "string", default: "utf8" },
        },
        required: ["path"],
    },
};
const WRITE_FILE_TOOL = {
    name: "write_file",
    description: "Write content to a file. Creates the file if it does not exist. " +
        "Optionally creates a backup of the previous content.",
    inputSchema: {
        type: "object",
        properties: {
            path: { type: "string", description: "Path to the file" },
            content: { type: "string", description: "Content to write" },
            encoding: { type: "string", default: "utf8" },
            backup: { type: "boolean", description: "Create backup before writing", default: true },
        },
        required: ["path", "content"],
    },
};
const EDIT_FILE_TOOL = {
    name: "edit_file",
    description: "Replace an exact string in a file with another string. " +
        "Fails if the old_string is not found exactly once (unless replace_all is true). " +
        "Always creates a backup before editing.",
    inputSchema: {
        type: "object",
        properties: {
            path: { type: "string", description: "Path to the file" },
            old_string: { type: "string", description: "Exact string to replace" },
            new_string: { type: "string", description: "Replacement string" },
            replace_all: { type: "boolean", description: "Replace all occurrences", default: false },
        },
        required: ["path", "old_string", "new_string"],
    },
};
const ROLLBACK_FILE_TOOL = {
    name: "rollback_file",
    description: "Restore the most recent backup of a file.",
    inputSchema: {
        type: "object",
        properties: {
            path: { type: "string", description: "Path to the file to restore" },
        },
        required: ["path"],
    },
};
const TOOLS = [READ_FILE_TOOL, WRITE_FILE_TOOL, EDIT_FILE_TOOL, ROLLBACK_FILE_TOOL];
async function handleReadFile(args) {
    const filePath = resolvePath(String(args.path));
    const encoding = args.encoding || "utf8";
    try {
        const content = await fs.readFile(filePath, { encoding: encoding });
        return {
            content: [{ type: "text", text: content }],
        };
    }
    catch (err) {
        if (err.code === "ENOENT")
            throw new Error(`File not found: ${args.path}`);
        if (err.code === "EACCES")
            throw new Error(`Permission denied: ${args.path}`);
        throw new Error(`Failed to read file: ${err.message}`);
    }
}
async function handleWriteFile(args) {
    const filePath = resolvePath(String(args.path));
    const content = String(args.content);
    const encoding = args.encoding || "utf8";
    const shouldBackup = args.backup !== false;
    let backupPath = null;
    try {
        if (shouldBackup) {
            backupPath = await createBackup(filePath);
        }
    }
    catch {
        // file may not exist yet — no backup needed
    }
    await fs.mkdir(path.dirname(filePath), { recursive: true });
    await fs.writeFile(filePath, content, { encoding: encoding });
    return {
        content: [
            {
                type: "text",
                text: JSON.stringify({
                    status: "written",
                    path: args.path,
                    bytes: Buffer.byteLength(content, encoding),
                    backup: backupPath,
                }, null, 2),
            },
        ],
    };
}
async function handleEditFile(args) {
    const filePath = resolvePath(String(args.path));
    const oldString = String(args.old_string);
    const newString = String(args.new_string);
    const replaceAll = args.replace_all === true;
    if (oldString === newString) {
        return {
            content: [{ type: "text", text: JSON.stringify({ status: "no_change", reason: "old_string equals new_string" }, null, 2) }],
        };
    }
    const content = await fs.readFile(filePath, "utf8");
    const occurrences = content.split(oldString).length - 1;
    if (occurrences === 0) {
        throw new Error(`old_string not found in file: ${args.path}`);
    }
    if (!replaceAll && occurrences > 1) {
        throw new Error(`old_string found ${occurrences} times in file. Set replace_all=true to replace all occurrences.`);
    }
    const backupPath = await createBackup(filePath);
    const newContent = replaceAll
        ? content.split(oldString).join(newString)
        : content.replace(oldString, newString);
    await fs.writeFile(filePath, newContent, "utf8");
    return {
        content: [
            {
                type: "text",
                text: JSON.stringify({
                    status: "edited",
                    path: args.path,
                    replacements: replaceAll ? occurrences : 1,
                    backup: backupPath,
                }, null, 2),
            },
        ],
    };
}
async function handleRollbackFile(args) {
    const filePath = resolvePath(String(args.path));
    const fileNameHash = Buffer.from(filePath).toString("base64url").slice(0, 16);
    const backups = await fs.readdir(BACKUP_DIR);
    const matching = backups
        .filter((b) => b.startsWith(fileNameHash + "_"))
        .sort()
        .reverse();
    if (matching.length === 0) {
        throw new Error(`No backup found for file: ${args.path}`);
    }
    const latestBackup = path.join(BACKUP_DIR, matching[0]);
    const content = await fs.readFile(latestBackup);
    await fs.writeFile(filePath, content);
    return {
        content: [
            {
                type: "text",
                text: JSON.stringify({ status: "restored", path: args.path, backup: latestBackup }, null, 2),
            },
        ],
    };
}
const server = new Server({ name: "mcp-replace", version: "1.0.0" }, { capabilities: { tools: {} } });
server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));
server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;
    switch (name) {
        case "read_file":
            return handleReadFile(args || {});
        case "write_file":
            return handleWriteFile(args || {});
        case "edit_file":
            return handleEditFile(args || {});
        case "rollback_file":
            return handleRollbackFile(args || {});
        default:
            throw new Error(`Unknown tool: ${name}`);
    }
});
async function main() {
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error("mcp-replace server running on stdio");
    console.error(`Base directory: ${BASE_DIR}`);
    console.error(`Backup directory: ${BACKUP_DIR}`);
}
main().catch((error) => {
    console.error("Fatal error:", error);
    process.exit(1);
});
//# sourceMappingURL=index.js.map