#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  Tool,
} from "@modelcontextprotocol/sdk/types.js";

const DEFAULT_TIMEOUT_MS = 30000;
const MAX_TIMEOUT_MS = 120000;
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1000;

// Simple in-memory rate limiter
const RATE_LIMIT_WINDOW_MS = 60_000;
const RATE_LIMIT_MAX_REQUESTS = 60;
const requestLog: number[] = [];

function checkRateLimit(): void {
  const now = Date.now();
  const windowStart = now - RATE_LIMIT_WINDOW_MS;
  while (requestLog.length > 0 && requestLog[0] < windowStart) {
    requestLog.shift();
  }
  if (requestLog.length >= RATE_LIMIT_MAX_REQUESTS) {
    throw new Error("Rate limit exceeded: too many requests in the last minute");
  }
  requestLog.push(now);
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const HTTP_REQUEST_TOOL: Tool = {
  name: "http_request",
  description:
    "Perform an HTTP request (GET, POST, PUT, DELETE, PATCH). " +
    "Supports headers, body, timeout, and automatic retries.",
  inputSchema: {
    type: "object",
    properties: {
      url: {
        type: "string",
        description: "Target URL",
      },
      method: {
        type: "string",
        description: "HTTP method",
        enum: ["GET", "POST", "PUT", "DELETE", "PATCH"],
        default: "GET",
      },
      headers: {
        type: "object",
        description: "HTTP headers",
        additionalProperties: { type: "string" },
      },
      body: {
        type: "string",
        description: "Request body (for POST, PUT, PATCH)",
      },
      timeout: {
        type: "number",
        description: "Timeout in milliseconds (default: 30000, max: 120000)",
        default: DEFAULT_TIMEOUT_MS,
      },
      retries: {
        type: "number",
        description: "Number of retries on failure (default: 3)",
        default: MAX_RETRIES,
      },
    },
    required: ["url"],
  },
};

const TOOLS: Tool[] = [HTTP_REQUEST_TOOL];

interface HttpResult {
  status: number;
  statusText: string;
  headers: Record<string, string>;
  body: string;
  finalUrl: string;
  retriesUsed: number;
  durationMs: number;
}

async function performFetch(
  url: string,
  options: RequestInit,
  timeout: number
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(timer);
    return response;
  } catch (err) {
    clearTimeout(timer);
    throw err;
  }
}

async function handleHttpRequest(args: Record<string, unknown>) {
  const url = String(args.url);
  const method = String(args.method || "GET").toUpperCase();
  const headers = (args.headers as Record<string, string>) || {};
  const body = args.body !== undefined ? String(args.body) : undefined;
  let timeout = Number(args.timeout || DEFAULT_TIMEOUT_MS);
  if (timeout <= 0 || timeout > MAX_TIMEOUT_MS) {
    timeout = DEFAULT_TIMEOUT_MS;
  }
  let retries = Number(args.retries !== undefined ? args.retries : MAX_RETRIES);
  if (retries < 0 || retries > 5) {
    retries = MAX_RETRIES;
  }

  checkRateLimit();

  const fetchOptions: RequestInit = {
    method,
    headers: {
      "User-Agent": "mcp-web/1.0.0",
      ...headers,
    },
  };
  if (body && ["POST", "PUT", "PATCH"].includes(method)) {
    fetchOptions.body = body;
  }

  let lastError: Error | null = null;
  let result: HttpResult | null = null;

  const startTime = Date.now();

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const response = await performFetch(url, fetchOptions, timeout);
      const responseBody = await response.text();
      const responseHeaders: Record<string, string> = {};
      response.headers.forEach((value, key) => {
        responseHeaders[key] = value;
      });
      result = {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
        body: responseBody,
        finalUrl: response.url,
        retriesUsed: attempt,
        durationMs: Date.now() - startTime,
      };
      break;
    } catch (err: any) {
      lastError = err;
      if (attempt < retries) {
        await sleep(RETRY_DELAY_MS * (attempt + 1));
      }
    }
  }

  if (!result) {
    throw new Error(
      `HTTP request failed after ${retries + 1} attempt(s): ${lastError?.message || "Unknown error"}`
    );
  }

  // Truncate very large bodies
  let bodyText = result.body;
  const MAX_BODY_LENGTH = 100_000;
  if (bodyText.length > MAX_BODY_LENGTH) {
    bodyText = bodyText.slice(0, MAX_BODY_LENGTH) + "\n...[truncated]";
  }

  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(
          {
            status: result.status,
            statusText: result.statusText,
            headers: result.headers,
            body: bodyText,
            finalUrl: result.finalUrl,
            retriesUsed: result.retriesUsed,
            durationMs: result.durationMs,
          },
          null,
          2
        ),
      },
    ],
  };
}

const server = new Server(
  { name: "mcp-web", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  switch (name) {
    case "http_request":
      return handleHttpRequest(args || {});
    default:
      throw new Error(`Unknown tool: ${name}`);
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("mcp-web server running on stdio");
}

main().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});
