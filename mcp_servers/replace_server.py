from __future__ import annotations

import difflib
import hashlib
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

from .base import MCPServer


class ReplaceMCPServer(MCPServer):
    """MCP server for tools_replace — file editing pipeline (safety-gated)."""

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="tools_replace", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()
        self._backup_dir = self.workspace / ".backup"
        self._backup_dir.mkdir(exist_ok=True)

        self.register("create_backup", "Create timestamped backup of a file before editing",
                       self._s({"path": "string"}), self.create_backup)
        self.register("match_pattern", "Find exact text to replace in a file",
                       self._s({"path": "string", "pattern": "string", "first_only?": "bool"}), self.match_pattern)
        self.register("apply_edit", "Apply exact string replacement in a file",
                       self._s({"path": "string", "old_string": "string", "new_string": "string",
                                "replace_all?": "bool"}), self.apply_edit)
        self.register("generate_diff", "Generate unified diff between original and modified content",
                       self._s({"path": "string", "original": "string", "modified": "string"}), self.generate_diff)
        self.register("rank_edit_candidates", "Rank multiple edit strategies by safety and impact",
                       self._s({"path": "string", "candidates": "array"}), self.rank_edit_candidates)
        self.register("validate_edit", "Validate edit result — check syntax, verify no corruption",
                       self._s({"path": "string", "content": "string"}), self.validate_edit)
        self.register("write_file", "Write content to file after validation",
                       self._s({"path": "string", "content": "string"}), self.write_file)
        self.register("verify_write", "Verify written file matches expected content via hash",
                       self._s({"path": "string", "expected_hash": "string"}), self.verify_write)
        self.register("rollback", "Rollback file to backup by timestamp",
                       self._s({"path": "string", "backup_id?": "string"}), self.rollback)
        self.register("safe_delete", "Safely delete a file with backup",
                       self._s({"path": "string"}), self.safe_delete)

    def _resolve(self, path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = self.workspace / p
        return p.resolve()

    async def create_backup(self, path: str) -> dict[str, Any]:
        filepath = self._resolve(path)
        if not filepath.exists():
            return {"error": f"File not found: {path}"}
        backup_id = f"{filepath.name}.{int(time.time() * 1000)}.bak"
        backup_path = self._backup_dir / backup_id
        shutil.copy2(filepath, backup_path)
        return {"path": str(filepath), "backup_id": backup_id, "backup_path": str(backup_path),
                "size": filepath.stat().st_size}

    async def match_pattern(self, path: str, pattern: str, first_only: bool = False) -> dict[str, Any]:
        filepath = self._resolve(path)
        if not filepath.exists():
            return {"error": f"File not found: {path}"}
        content = filepath.read_text(encoding="utf-8")
        matches: list[dict[str, Any]] = []
        start = 0
        while True:
            idx = content.find(pattern, start)
            if idx == -1:
                break
            line_num = content[:idx].count("\n") + 1
            matches.append({"position": idx, "line": line_num, "length": len(pattern),
                            "context": content[max(0,idx-40):idx+len(pattern)+40]})
            if first_only:
                break
            start = idx + 1
        return {"path": str(filepath), "matches": matches, "count": len(matches)}

    async def apply_edit(self, path: str, old_string: str, new_string: str,
                         replace_all: bool = False) -> dict[str, Any]:
        filepath = self._resolve(path)
        if not filepath.exists():
            return {"error": f"File not found: {path}"}
        content = filepath.read_text(encoding="utf-8")
        if old_string not in content:
            return {"error": "Pattern not found in file", "path": str(filepath)}

        count = content.count(old_string) if replace_all else 1
        new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)

        await self.create_backup(path)
        filepath.write_text(new_content, encoding="utf-8")
        return {"path": str(filepath), "replaced": True, "occurrences": count,
                "old_size": len(content), "new_size": len(new_content)}

    async def generate_diff(self, path: str, original: str, modified: str) -> dict[str, Any]:
        diff = list(difflib.unified_diff(
            original.split("\n"), modified.split("\n"),
            fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=""
        ))
        return {"path": path, "diff": "\n".join(diff), "added_lines": sum(1 for d in diff if d.startswith("+") and not d.startswith("+++")),
                "removed_lines": sum(1 for d in diff if d.startswith("-") and not d.startswith("---"))}

    async def rank_edit_candidates(self, path: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        for c in candidates:
            score = 0
            old = c.get("old_string", "")
            new = c.get("new_string", "")
            score += min(len(old), 50) / 50 * 30
            score += (20 if old != new else 0)
            score += (30 if len(new) <= len(old) * 1.5 else 10)
            filepath = self._resolve(path)
            if filepath.exists():
                content = filepath.read_text(encoding="utf-8")
                if old in content:
                    score += 20
                if old == new:
                    score -= 50
            c["score"] = min(100, max(0, score))
        candidates.sort(key=lambda c: c.get("score", 0), reverse=True)
        return {"candidates": candidates, "top_score": candidates[0]["score"] if candidates else 0}

    async def validate_edit(self, path: str, content: str) -> dict[str, Any]:
        issues: list[str] = []
        if not content.strip():
            issues.append("File would be empty")
        if content.count("\0") > 0:
            issues.append("Contains null bytes — possible binary corruption")
        ext = Path(path).suffix
        if ext == ".py":
            try:
                compile(content, path, "exec")
            except SyntaxError as e:
                issues.append(f"Python syntax error: {e}")
        elif ext in (".json",):
            import json
            try:
                json.loads(content)
            except json.JSONDecodeError as e:
                issues.append(f"JSON parse error: {e}")
        return {"path": path, "valid": len(issues) == 0, "issues": issues,
                "size": len(content), "line_count": content.count("\n") + 1}

    async def write_file(self, path: str, content: str) -> dict[str, Any]:
        filepath = self._resolve(path)
        if filepath.exists():
            await self.create_backup(path)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        return {"path": str(filepath), "written": True, "size": len(content),
                "lines": content.count("\n") + 1}

    async def verify_write(self, path: str, expected_hash: str) -> dict[str, Any]:
        filepath = self._resolve(path)
        if not filepath.exists():
            return {"error": f"File not found: {path}", "match": False}
        actual = hashlib.sha256(filepath.read_bytes()).hexdigest()
        return {"path": str(filepath), "match": actual == expected_hash, "actual_hash": actual}

    async def rollback(self, path: str, backup_id: str = "") -> dict[str, Any]:
        filepath = self._resolve(path)
        if backup_id:
            backup_path = self._backup_dir / backup_id
        else:
            backups = sorted(self._backup_dir.glob(f"{filepath.name}.*.bak"), reverse=True)
            if not backups:
                return {"error": "No backups found", "path": str(filepath)}
            backup_path = backups[0]

        if not backup_path.exists():
            return {"error": f"Backup not found: {backup_id}"}
        shutil.copy2(backup_path, filepath)
        return {"path": str(filepath), "rolled_back": True, "backup_id": backup_path.name}

    async def safe_delete(self, path: str) -> dict[str, Any]:
        filepath = self._resolve(path)
        if not filepath.exists():
            return {"error": f"File not found: {path}"}
        await self.create_backup(path)
        filepath.unlink()
        return {"path": str(filepath), "deleted": True}

    @staticmethod
    def _s(props: dict[str, str]) -> dict[str, Any]:
        required = [k for k in props if not k.endswith("?")]
        properties = {}
        for k, v in props.items():
            name = k.rstrip("?")
            type_map = {"string": "string", "int": "integer", "bool": "boolean", "float": "number", "array": "array"}
            properties[name] = {"type": type_map.get(v, "string"), "description": f"The {name} parameter"}
        return {"type": "object", "properties": properties, "required": required}
