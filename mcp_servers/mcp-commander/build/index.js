#!/usr/bin/env node
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema, } from "@modelcontextprotocol/sdk/types.js";
import { spawn } from "child_process";
import path from "path";
const BASE_DIR = process.env.MCP_BASE_DIR || process.cwd();
const DEFAULT_TIMEOUT_MS = 30000;
const MAX_TIMEOUT_MS = 120000;
const DANGEROUS_PATTERNS = [
    /rm\s+-rf\s+\/(?!\w)/,
    /mkfs/,
    /dd\s+if=.*of=\/dev\/sd/,
    /:\s*\(\s*\)\s*{\s*:\s*\|:\s*&\s*};\s*:/,
    />\s*\/dev\/sd/,
    /:\s*\(\)\s*{\s*:\s*\|\s*:\s*&\s*};\s*:\s*\(\)/,
    /format\s+/,
    /del\s+\/f\s+\/s\s+\/q/,
    /rmdir\s+\/s\s+\/q/,
];
function resolvePath(targetPath) {
    const resolved = path.resolve(BASE_DIR, targetPath);
    const normalizedBase = path.normalize(BASE_DIR);
    const normalizedTarget = path.normalize(resolved);
    if (!normalizedTarget.startsWith(normalizedBase)) {
        throw new Error(`Access denied: path "${targetPath}" escapes the allowed base directory "${BASE_DIR}"`);
    }
    return resolved;
}
function validateCommand(command) {
    const lower = command.toLowerCase();
    for (const pattern of DANGEROUS_PATTERNS) {
        if (pattern.test(lower)) {
            throw new Error(`Command blocked by security policy: matches dangerous pattern "${pattern.source}"`);
        }
    }
}
const EXECUTE_COMMAND_TOOL = {
    name: "execute_command",
    description: "Execute a shell command within the allowed base directory. " +
        "Dangerous patterns (rm -rf /, mkfs, dd to block devices, etc.) are blocked. " +
        "Output is capped and a timeout is enforced.",
    inputSchema: {
        type: "object",
        properties: {
            command: {
                type: "string",
                description: "The shell command to execute",
            },
            cwd: {
                type: "string",
                description: "Working directory relative to the base directory (default: base directory)",
                default: ".",
            },
            timeout: {
                type: "number",
                description: "Timeout in milliseconds (default: 30000, max: 120000)",
                default: DEFAULT_TIMEOUT_MS,
            },
            env: {
                type: "object",
                description: "Additional environment variables",
                additionalProperties: { type: "string" },
            },
        },
        required: ["command"],
    },
};
const TOOLS = [EXECUTE_COMMAND_TOOL];
function handleExecuteCommand(args) {
    const command = String(args.command);
    const cwd = resolvePath(String(args.cwd || "."));
    let timeout = Number(args.timeout || DEFAULT_TIMEOUT_MS);
    if (timeout <= 0 || timeout > MAX_TIMEOUT_MS) {
        timeout = DEFAULT_TIMEOUT_MS;
    }
    validateCommand(command);
    const mergedEnv = { ...process.env, ...(args.env || {}) };
    return new Promise((resolve, reject) => {
        const shell = process.platform === "win32" ? "cmd.exe" : "/bin/sh";
        const shellFlag = process.platform === "win32" ? "/c" : "-c";
        const child = spawn(shell, [shellFlag, command], {
            cwd,
            env: mergedEnv,
            stdio: ["ignore", "pipe", "pipe"],
        });
        let stdout = "";
        let stderr = "";
        let killed = false;
        const timer = setTimeout(() => {
            killed = true;
            child.kill("SIGTERM");
            setTimeout(() => child.kill("SIGKILL"), 5000);
        }, timeout);
        child.stdout?.on("data", (data) => {
            stdout += data.toString("utf8");
            if (stdout.length > 500_000) {
                stdout = stdout.slice(0, 500_000) + "\n...[truncated]";
                child.stdout?.pause();
            }
        });
        child.stderr?.on("data", (data) => {
            stderr += data.toString("utf8");
            if (stderr.length > 500_000) {
                stderr = stderr.slice(0, 500_000) + "\n...[truncated]";
                child.stderr?.pause();
            }
        });
        child.on("error", (err) => {
            clearTimeout(timer);
            reject(new Error(`Failed to start command: ${err.message}`));
        });
        child.on("close", (code, signal) => {
            clearTimeout(timer);
            const result = {
                stdout: stdout.trimEnd(),
                stderr: stderr.trimEnd(),
                exit_code: code,
                signal: signal || null,
                timed_out: killed,
            };
            resolve({
                content: [
                    {
                        type: "text",
                        text: JSON.stringify(result, null, 2),
                    },
                ],
            });
        });
    });
}
const server = new Server({
    name: "mcp-commander",
    version: "1.0.0",
}, {
    capabilities: {
        tools: {},
    },
});
server.setRequestHandler(ListToolsRequestSchema, async () => {
    return { tools: TOOLS };
});
server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;
    switch (name) {
        case "execute_command":
            return handleExecuteCommand(args || {});
        default:
            throw new Error(`Unknown tool: ${name}`);
    }
});
async function main() {
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error("mcp-commander server running on stdio");
    console.error(`Base directory: ${BASE_DIR}`);
}
main().catch((error) => {
    console.error("Fatal error:", error);
    process.exit(1);
});
//# sourceMappingURL=index.js.map