from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any

from .base import MCPServer, MCPToolResult


class ReadMCPServer(MCPServer):
    """MCP server for tools_read — file reading pipeline (linear)."""

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="tools_read", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()
        self._cache: dict[str, tuple[float, str]] = {}

        self._register_all()

    def _register_all(self):
        self.register("read_file", "Read file content with encoding detection and caching",
                       self._schema({"path": "string", "encoding?": "string", "start_line?": "int", "end_line?": "int"}),
                       self.read_file)

        self.register("detect_encoding", "Detect file encoding and BOM",
                       self._schema({"path": "string"}),
                       self.detect_encoding)

        self.register("get_file_info", "Get file metadata — size, modification time, MIME type, line count",
                       self._schema({"path": "string"}),
                       self.get_file_info)

        self.register("read_chunk", "Read a specific chunk of a file by line range",
                       self._schema({"path": "string", "start_line": "int", "end_line": "int"}),
                       self.read_chunk)

        self.register("extract_content", "Extract specific content from file by regex pattern",
                       self._schema({"path": "string", "pattern": "string", "group?": "int"}),
                       self.extract_content)

        self.register("validate_integrity", "Validate file integrity via SHA256 hash",
                       self._schema({"path": "string", "expected_hash?": "string"}),
                       self.validate_integrity)

        self.register("format_output", "Format file content for display — truncate, highlight, line numbers",
                       self._schema({"content": "string", "max_lines?": "int", "show_line_numbers?": "bool"}),
                       self.format_output)

        self.register("list_directory", "List files in a directory with optional glob filter",
                       self._schema({"path": "string", "pattern?": "string", "recursive?": "bool"}),
                       self.list_directory)

        self.register("clear_cache", "Clear the file read cache",
                       self._schema({}),
                       self.clear_cache)

    def _resolve(self, path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = self.workspace / p
        resolved = p.resolve()
        if not str(resolved).startswith(str(self.workspace)):
            raise PermissionError(f"Access denied: {path} is outside workspace")
        return resolved

    async def read_file(self, path: str, encoding: str = "utf-8", start_line: int = 0, end_line: int = 0) -> dict[str, Any]:
        filepath = self._resolve(path)
        if not filepath.exists():
            return {"error": f"File not found: {path}", "content": None}

        content = filepath.read_text(encoding=encoding)
        lines = content.split("\n")

        if start_line > 0 or end_line > 0:
            start = max(0, start_line - 1) if start_line > 0 else 0
            end_val = end_line if end_line > 0 else len(lines)
            lines = lines[start:end_val]
            content = "\n".join(lines)

        self._cache[path] = (time.time(), content)
        return {
            "content": content,
            "path": str(filepath),
            "total_lines": len(lines) if start_line == 0 and end_line == 0 else len(filepath.read_text(encoding).split("\n")),
            "size_bytes": filepath.stat().st_size,
            "encoding": encoding,
        }

    async def detect_encoding(self, path: str) -> dict[str, Any]:
        filepath = self._resolve(path)
        raw = filepath.read_bytes()
        result = {"path": str(filepath), "encoding": "utf-8", "bom": None}
        if raw.startswith(b"\xef\xbb\xbf"):
            result["encoding"], result["bom"] = "utf-8-sig", "UTF-8 BOM"
        elif raw.startswith(b"\xff\xfe"):
            result["encoding"], result["bom"] = "utf-16-le", "UTF-16 LE BOM"
        elif raw.startswith(b"\xfe\xff"):
            result["encoding"], result["bom"] = "utf-16-be", "UTF-16 BE BOM"
        return result

    async def get_file_info(self, path: str) -> dict[str, Any]:
        filepath = self._resolve(path)
        if not filepath.exists():
            return {"error": f"File not found: {path}"}

        stat = filepath.stat()
        mime_type, _ = mimetypes.guess_type(str(filepath))
        try:
            content = filepath.read_text()
            line_count = content.count("\n") + 1
            char_count = len(content)
        except Exception:
            line_count = 0
            char_count = 0

        return {
            "path": str(filepath),
            "size_bytes": stat.st_size,
            "modified_at": stat.st_mtime,
            "created_at": stat.st_ctime,
            "mime_type": mime_type or "unknown",
            "extension": filepath.suffix,
            "line_count": line_count,
            "char_count": char_count,
        }

    async def read_chunk(self, path: str, start_line: int, end_line: int) -> dict[str, Any]:
        return await self.read_file(path=path, start_line=start_line, end_line=end_line)

    async def extract_content(self, path: str, pattern: str, group: int = 0) -> dict[str, Any]:
        import re
        filepath = self._resolve(path)
        content = filepath.read_text()
        matches = re.findall(pattern, content)
        return {"path": str(filepath), "pattern": pattern, "matches": matches, "count": len(matches)}

    async def validate_integrity(self, path: str, expected_hash: str = "") -> dict[str, Any]:
        filepath = self._resolve(path)
        content = filepath.read_bytes()
        sha = hashlib.sha256(content).hexdigest()
        return {"path": str(filepath), "sha256": sha, "match": sha == expected_hash if expected_hash else None}

    async def format_output(self, content: str, max_lines: int = 200, show_line_numbers: bool = False) -> dict[str, Any]:
        lines = content.split("\n")
        truncated = len(lines) > max_lines
        if truncated:
            lines = lines[:max_lines]

        if show_line_numbers:
            width = len(str(len(lines)))
            lines = [f"{i+1:>{width}}  {line}" for i, line in enumerate(lines)]

        return {"formatted": "\n".join(lines), "total_lines": len(lines), "truncated": truncated}

    async def list_directory(self, path: str, pattern: str = "*", recursive: bool = False) -> dict[str, Any]:
        import fnmatch
        dirpath = self._resolve(path)
        if not dirpath.is_dir():
            return {"error": f"Not a directory: {path}"}

        entries = []
        iterator = dirpath.rglob(pattern) if recursive else dirpath.glob(pattern)
        for p in iterator:
            if p.name.startswith("."):
                continue
            entries.append({"name": p.name, "path": str(p), "type": "dir" if p.is_dir() else "file",
                            "size": p.stat().st_size if p.is_file() else 0})
        return {"path": str(dirpath), "entries": sorted(entries, key=lambda e: (e["type"], e["name"])),
                "count": len(entries)}

    async def clear_cache(self) -> dict[str, Any]:
        count = len(self._cache)
        self._cache.clear()
        return {"cleared": count}

    @staticmethod
    def _schema(props: dict[str, str]) -> dict[str, Any]:
        required = [k for k in props if not k.endswith("?")]
        properties = {}
        for k, v in props.items():
            name = k.rstrip("?")
            type_map = {"string": "string", "int": "integer", "bool": "boolean", "float": "number"}
            properties[name] = {"type": type_map.get(v, "string"), "description": f"The {name} parameter"}
        return {"type": "object", "properties": properties, "required": required}
