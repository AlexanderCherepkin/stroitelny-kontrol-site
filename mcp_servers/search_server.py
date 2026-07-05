from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

from .base import MCPServer


class SearchMCPServer(MCPServer):
    """MCP server for tools_search — code search pipeline (diamond)."""

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="tools_search", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()

        self.register("regex_search", "Search using regex patterns across files",
                       self._s({"query": "string", "path?": "string", "glob?": "string",
                                "max_results?": "int", "context_lines?": "int", "case_sensitive?": "bool"}),
                       self.regex_search)

        self.register("semantic_search", "Semantic search using keyword relevance ranking",
                       self._s({"query": "string", "path?": "string", "glob?": "string", "max_results?": "int"}),
                       self.semantic_search)

        self.register("define_scope", "Define search scope by directory or file pattern",
                       self._s({"path": "string", "include?": "string", "exclude?": "string"}),
                       self.define_scope)

        self.register("rank_relevance", "Rank search results by relevance score",
                       self._s({"query": "string", "results": "array"}),
                       self.rank_relevance)

        self.register("deduplicate", "Remove duplicate or near-duplicate search results",
                       self._s({"results": "array", "similarity_threshold?": "float"}),
                       self.deduplicate)

        self.register("generate_snippet", "Generate contextual code snippets around matches",
                       self._s({"file_path": "string", "line_number": "int", "context_lines?": "int"}),
                       self.generate_snippet)

        self.register("find_symbol", "Find a symbol (function, class, variable) definition in code",
                       self._s({"symbol": "string", "path?": "string", "symbol_type?": "string"}),
                       self.find_symbol)

        self.register("diff_search", "Search for differences between two strings or files",
                       self._s({"a": "string", "b": "string", "context_lines?": "int"}),
                       self.diff_search)

    def _resolve(self, path: str = ".") -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = self.workspace / p
        return p.resolve()

    async def regex_search(self, query: str, path: str = ".", glob: str = "*",
                           max_results: int = 50, context_lines: int = 2,
                           case_sensitive: bool = False) -> dict[str, Any]:
        import fnmatch
        search_path = self._resolve(path)
        flags = 0 if case_sensitive else re.IGNORECASE
        results: list[dict[str, Any]] = []
        files_scanned = 0

        try:
            pattern = re.compile(query, flags)
        except re.error as e:
            return {"error": f"Invalid regex: {e}", "results": []}

        iterator = search_path.rglob(glob) if "**" in glob or search_path.is_dir() else [search_path]
        if search_path.is_dir() and "**" not in glob:
            iterator = search_path.glob(glob)

        for filepath in iterator:
            if not filepath.is_file():
                continue
            if filepath.name.startswith(".") or "node_modules" in str(filepath):
                continue
            try:
                lines = filepath.read_text(encoding="utf-8", errors="replace").split("\n")
                files_scanned += 1
                for i, line in enumerate(lines):
                    if pattern.search(line):
                        ctx_start = max(0, i - context_lines)
                        ctx_end = min(len(lines), i + context_lines + 1)
                        results.append({
                            "file": str(filepath),
                            "line": i + 1,
                            "match": line.strip()[:200],
                            "context": "\n".join(f"{j+1}: {lines[j].rstrip()}" for j in range(ctx_start, ctx_end)),
                        })
                        if len(results) >= max_results:
                            break
            except (PermissionError, OSError):
                continue
            if len(results) >= max_results:
                break

        return {"results": results, "count": len(results), "files_scanned": files_scanned, "query": query}

    async def semantic_search(self, query: str, path: str = ".", glob: str = "*",
                              max_results: int = 30) -> dict[str, Any]:
        query_terms = set(query.lower().split())
        results = await self.regex_search(query="|".join(re.escape(t) for t in query_terms),
                                          path=path, glob=glob, max_results=max_results * 2)
        for r in results.get("results", []):
            match_lower = r["match"].lower()
            score = sum(1 for t in query_terms if t in match_lower)
            r["relevance"] = score / len(query_terms) if query_terms else 0
        results["results"].sort(key=lambda r: r.get("relevance", 0), reverse=True)
        results["results"] = results["results"][:max_results]
        results["query_terms"] = list(query_terms)
        return results

    async def define_scope(self, path: str, include: str = "", exclude: str = "") -> dict[str, Any]:
        p = self._resolve(path)
        if not p.exists():
            return {"error": f"Path not found: {path}"}
        file_count = sum(1 for _ in p.rglob("*")) if p.is_dir() else 1
        return {"path": str(p), "type": "directory" if p.is_dir() else "file",
                "include": include or "*", "exclude": exclude or "none",
                "estimated_files": file_count}

    async def rank_relevance(self, query: str, results: list[dict[str, Any]]) -> dict[str, Any]:
        terms = query.lower().split()
        for r in results:
            text = (r.get("match", "") + " " + r.get("file", "")).lower()
            r["relevance"] = sum(1 for t in terms if t in text) / max(len(terms), 1)
        results.sort(key=lambda r: r.get("relevance", 0), reverse=True)
        return {"results": results, "count": len(results)}

    async def deduplicate(self, results: list[dict[str, Any]],
                          similarity_threshold: float = 0.85) -> dict[str, Any]:
        unique: list[dict[str, Any]] = []
        seen = set()
        for r in results:
            key = f"{r.get('file','')}:{r.get('line','')}"
            if key not in seen:
                seen.add(key)
                unique.append(r)
        return {"results": unique, "original_count": len(results), "unique_count": len(unique)}

    async def generate_snippet(self, file_path: str, line_number: int,
                               context_lines: int = 3) -> dict[str, Any]:
        p = self._resolve(file_path)
        if not p.exists():
            return {"error": f"File not found: {file_path}"}
        lines = p.read_text(encoding="utf-8", errors="replace").split("\n")
        target = line_number - 1
        start = max(0, target - context_lines)
        end = min(len(lines), target + context_lines + 1)
        return {
            "file": str(p),
            "target_line": line_number,
            "snippet": "\n".join(f"{j+1}: {lines[j].rstrip()}" for j in range(start, end)),
        }

    async def find_symbol(self, symbol: str, path: str = ".",
                          symbol_type: str = "any") -> dict[str, Any]:
        patterns = {
            "function": rf"def\s+{re.escape(symbol)}\s*\(",
            "class": rf"class\s+{re.escape(symbol)}\s*[:(]",
            "variable": rf"^{re.escape(symbol)}\s*=",
            "any": rf"(def|class)\s+{re.escape(symbol)}\b|^{re.escape(symbol)}\s*=",
        }
        pattern = patterns.get(symbol_type, patterns["any"])
        return await self.regex_search(query=pattern, path=path, context_lines=5)

    async def diff_search(self, a: str, b: str, context_lines: int = 3) -> dict[str, Any]:
        a_lines = a.split("\n")
        b_lines = b.split("\n")

        # Simple line diff
        diffs: list[dict[str, Any]] = []
        max_len = max(len(a_lines), len(b_lines))
        for i in range(max_len):
            a_line = a_lines[i] if i < len(a_lines) else None
            b_line = b_lines[i] if i < len(b_lines) else None
            if a_line != b_line:
                diffs.append({"line": i + 1, "removed": a_line, "added": b_line})

        return {"differences": diffs, "count": len(diffs),
                "a_lines": len(a_lines), "b_lines": len(b_lines)}

    @staticmethod
    def _s(props: dict[str, str]) -> dict[str, Any]:
        required = [k for k in props if not k.endswith("?")]
        properties = {}
        for k, v in props.items():
            name = k.rstrip("?")
            type_map = {"string": "string", "int": "integer", "bool": "boolean", "float": "number", "array": "array"}
            properties[name] = {"type": type_map.get(v, "string"), "description": f"The {name} parameter"}
        return {"type": "object", "properties": properties, "required": required}
