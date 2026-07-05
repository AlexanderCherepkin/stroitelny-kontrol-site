#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  Tool,
} from "@modelcontextprotocol/sdk/types.js";
import fs from "fs/promises";
import type { Dirent } from "fs";
import path from "path";

const BASE_DIR = process.env.MCP_BASE_DIR || process.cwd();

function resolvePath(targetPath: string): string {
  const resolved = path.resolve(BASE_DIR, targetPath);
  const normalizedBase = path.normalize(BASE_DIR);
  const normalizedTarget = path.normalize(resolved);

  if (!normalizedTarget.startsWith(normalizedBase)) {
    throw new Error(
      `Access denied: path "${targetPath}" escapes the allowed base directory "${BASE_DIR}"`
    );
  }
  return resolved;
}

const READ_FILE_TOOL: Tool = {
  name: "read_file",
  description:
    "Read the contents of a file. " +
    "Only reads files within the allowed base directory.",
  inputSchema: {
    type: "object",
    properties: {
      path: {
        type: "string",
        description: "Absolute or relative path to the file (resolved against base directory)",
      },
      encoding: {
        type: "string",
        description: "File encoding (default: utf8)",
        default: "utf8",
      },
    },
    required: ["path"],
  },
};

const LIST_DIRECTORY_TOOL: Tool = {
  name: "list_directory",
  description:
    "List files and directories at the given path. " +
    "Only accesses directories within the allowed base directory.",
  inputSchema: {
    type: "object",
    properties: {
      path: {
        type: "string",
        description: "Absolute or relative path to the directory (resolved against base directory)",
        default: ".",
      },
    },
    required: [],
  },
};

const TOOLS: Tool[] = [READ_FILE_TOOL, LIST_DIRECTORY_TOOL];

async function handleReadFile(args: Record<string, unknown>) {
  const filePath = resolvePath(String(args.path));
  const encoding = (args.encoding as string) || "utf8";

  try {
    const content = await fs.readFile(filePath, { encoding: encoding as BufferEncoding });
    return {
      content: [
        {
          type: "text",
          text: content,
        },
      ],
    };
  } catch (err: any) {
    if (err.code === "ENOENT") {
      throw new Error(`File not found: ${args.path}`);
    }
    if (err.code === "EACCES") {
      throw new Error(`Permission denied: ${args.path}`);
    }
    throw new Error(`Failed to read file: ${err.message}`);
  }
}

async function handleListDirectory(args: Record<string, unknown>) {
  const dirPath = resolvePath(String(args.path || "."));

  try {
    const entries = await fs.readdir(dirPath, { withFileTypes: true });
    const result = entries.map((entry: Dirent) => ({
      name: entry.name,
      type: entry.isDirectory() ? "directory" : "file",
    }));

    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(result, null, 2),
        },
      ],
    };
  } catch (err: any) {
    if (err.code === "ENOENT") {
      throw new Error(`Directory not found: ${args.path || "."}`);
    }
    if (err.code === "EACCES") {
      throw new Error(`Permission denied: ${args.path || "."}`);
    }
    throw new Error(`Failed to list directory: ${err.message}`);
  }
}

const server = new Server(
  {
    name: "mcp-filesystem",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return { tools: TOOLS };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  switch (name) {
    case "read_file":
      return handleReadFile(args || {});
    case "list_directory":
      return handleListDirectory(args || {});
    default:
      throw new Error(`Unknown tool: ${name}`);
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("mcp-filesystem server running on stdio");
  console.error(`Base directory: ${BASE_DIR}`);
}

main().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});
