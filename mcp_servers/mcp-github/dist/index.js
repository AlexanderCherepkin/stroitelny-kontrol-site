#!/usr/bin/env node
/**
 * MCP-GitHub Server
 * Provides PR API tools for Agentic Loop automatic review integration.
 *
 * Environment:
 *   GITHUB_TOKEN — Personal access token (required)
 *   GITHUB_API_URL — Override API base (default: https://api.github.com)
 *
 * Tools:
 *   - github_pr_list
 *   - github_pr_get
 *   - github_pr_diff
 *   - github_pr_review
 *   - github_pr_comments
 *   - github_pr_create_comment
 *   - github_issue_list
 */
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema, } from "@modelcontextprotocol/sdk/types.js";
const API_BASE = process.env.GITHUB_API_URL || "https://api.github.com";
const TOKEN = process.env.GITHUB_TOKEN || "";
function authHeaders() {
    const h = {
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "agentic-loop-mcp-github/1.0",
    };
    if (TOKEN) {
        h.Authorization = `Bearer ${TOKEN}`;
    }
    return h;
}
async function githubFetch(path, opts = {}) {
    const url = `${API_BASE}${path}`;
    const res = await fetch(url, {
        ...opts,
        headers: { ...authHeaders(), ...(opts.headers || {}) },
    });
    if (!res.ok) {
        const body = await res.text();
        throw new Error(`GitHub API ${res.status}: ${body}`);
    }
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
        return res.json();
    }
    return res.text();
}
// ── Tool definitions ───────────────────────────────────────────────────────
const TOOLS = [
    {
        name: "github_pr_list",
        description: "List open pull requests for a repository",
        inputSchema: {
            type: "object",
            properties: {
                owner: { type: "string", description: "Repository owner" },
                repo: { type: "string", description: "Repository name" },
                state: { type: "string", enum: ["open", "closed", "all"], default: "open" },
                per_page: { type: "number", default: 30 },
            },
            required: ["owner", "repo"],
        },
    },
    {
        name: "github_pr_get",
        description: "Get details of a specific pull request",
        inputSchema: {
            type: "object",
            properties: {
                owner: { type: "string" },
                repo: { type: "string" },
                pull_number: { type: "number" },
            },
            required: ["owner", "repo", "pull_number"],
        },
    },
    {
        name: "github_pr_diff",
        description: "Get the diff of a pull request",
        inputSchema: {
            type: "object",
            properties: {
                owner: { type: "string" },
                repo: { type: "string" },
                pull_number: { type: "number" },
            },
            required: ["owner", "repo", "pull_number"],
        },
    },
    {
        name: "github_pr_review",
        description: "Submit a review on a pull request",
        inputSchema: {
            type: "object",
            properties: {
                owner: { type: "string" },
                repo: { type: "string" },
                pull_number: { type: "number" },
                event: { type: "string", enum: ["APPROVE", "REQUEST_CHANGES", "COMMENT"], default: "COMMENT" },
                body: { type: "string", description: "Review summary comment" },
                comments: {
                    type: "array",
                    items: {
                        type: "object",
                        properties: {
                            path: { type: "string" },
                            line: { type: "number" },
                            body: { type: "string" },
                            side: { type: "string", enum: ["LEFT", "RIGHT"], default: "RIGHT" },
                        },
                        required: ["path", "line", "body"],
                    },
                },
            },
            required: ["owner", "repo", "pull_number", "event", "body"],
        },
    },
    {
        name: "github_pr_comments",
        description: "List review comments on a pull request",
        inputSchema: {
            type: "object",
            properties: {
                owner: { type: "string" },
                repo: { type: "string" },
                pull_number: { type: "number" },
            },
            required: ["owner", "repo", "pull_number"],
        },
    },
    {
        name: "github_pr_create_comment",
        description: "Create a single review comment on a pull request diff",
        inputSchema: {
            type: "object",
            properties: {
                owner: { type: "string" },
                repo: { type: "string" },
                pull_number: { type: "number" },
                commit_id: { type: "string" },
                path: { type: "string" },
                line: { type: "number" },
                body: { type: "string" },
                side: { type: "string", enum: ["LEFT", "RIGHT"], default: "RIGHT" },
            },
            required: ["owner", "repo", "pull_number", "commit_id", "path", "line", "body"],
        },
    },
    {
        name: "github_issue_list",
        description: "List issues for a repository",
        inputSchema: {
            type: "object",
            properties: {
                owner: { type: "string" },
                repo: { type: "string" },
                state: { type: "string", enum: ["open", "closed", "all"], default: "open" },
                labels: { type: "string", description: "Comma-separated label list" },
                per_page: { type: "number", default: 30 },
            },
            required: ["owner", "repo"],
        },
    },
];
// ── Handlers ───────────────────────────────────────────────────────────────
async function handlePrList(args) {
    const owner = String(args.owner);
    const repo = String(args.repo);
    const state = String(args.state || "open");
    const per_page = Number(args.per_page || 30);
    const data = await githubFetch(`/repos/${owner}/${repo}/pulls?state=${state}&per_page=${per_page}`);
    return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
}
async function handlePrGet(args) {
    const owner = String(args.owner);
    const repo = String(args.repo);
    const num = Number(args.pull_number);
    const data = await githubFetch(`/repos/${owner}/${repo}/pulls/${num}`);
    return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
}
async function handlePrDiff(args) {
    const owner = String(args.owner);
    const repo = String(args.repo);
    const num = Number(args.pull_number);
    const data = await githubFetch(`/repos/${owner}/${repo}/pulls/${num}`, {
        headers: { Accept: "application/vnd.github.diff" },
    });
    return { content: [{ type: "text", text: String(data) }] };
}
async function handlePrReview(args) {
    const owner = String(args.owner);
    const repo = String(args.repo);
    const num = Number(args.pull_number);
    const body = {
        event: args.event,
        body: args.body,
        comments: args.comments || [],
    };
    const data = await githubFetch(`/repos/${owner}/${repo}/pulls/${num}/reviews`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
}
async function handlePrComments(args) {
    const owner = String(args.owner);
    const repo = String(args.repo);
    const num = Number(args.pull_number);
    const data = await githubFetch(`/repos/${owner}/${repo}/pulls/${num}/comments`);
    return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
}
async function handlePrCreateComment(args) {
    const owner = String(args.owner);
    const repo = String(args.repo);
    const num = Number(args.pull_number);
    const body = {
        commit_id: args.commit_id,
        path: args.path,
        line: args.line,
        body: args.body,
        side: args.side || "RIGHT",
    };
    const data = await githubFetch(`/repos/${owner}/${repo}/pulls/${num}/comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
}
async function handleIssueList(args) {
    const owner = String(args.owner);
    const repo = String(args.repo);
    const state = String(args.state || "open");
    const per_page = Number(args.per_page || 30);
    let url = `/repos/${owner}/${repo}/issues?state=${state}&per_page=${per_page}`;
    if (args.labels) {
        url += `&labels=${encodeURIComponent(String(args.labels))}`;
    }
    const data = await githubFetch(url);
    return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
}
// ── Server wiring ────────────────────────────────────────────────────────────
const server = new Server({ name: "mcp-github", version: "1.0.0" }, { capabilities: { tools: {} } });
server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));
server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args = {} } = request.params;
    switch (name) {
        case "github_pr_list":
            return handlePrList(args);
        case "github_pr_get":
            return handlePrGet(args);
        case "github_pr_diff":
            return handlePrDiff(args);
        case "github_pr_review":
            return handlePrReview(args);
        case "github_pr_comments":
            return handlePrComments(args);
        case "github_pr_create_comment":
            return handlePrCreateComment(args);
        case "github_issue_list":
            return handleIssueList(args);
        default:
            throw new Error(`Unknown tool: ${name}`);
    }
});
async function main() {
    if (!TOKEN) {
        console.error("GITHUB_TOKEN environment variable is required");
        process.exit(1);
    }
    const transport = new StdioServerTransport();
    await server.connect(transport);
}
main().catch((err) => {
    console.error("Fatal error:", err);
    process.exit(1);
});
