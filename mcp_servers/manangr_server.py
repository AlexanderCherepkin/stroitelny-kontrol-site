from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from .base import MCPServer


class ManangrMCPServer(MCPServer):
    """MCP server for tools_manangr — project management pipeline (analysis-planning)."""

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="tools_manangr", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()

        self.register("analyze_structure", "Analyze project directory structure — files, sizes, languages",
                       self._s({"path?": "string", "max_depth?": "int"}), self.analyze_structure)
        self.register("map_dependencies", "Map dependencies between modules/files in the project",
                       self._s({"path?": "string", "language?": "string"}), self.map_dependencies)
        self.register("analyze_impact", "Analyze impact of changing a file — what depends on it?",
                       self._s({"file_path": "string", "change_type?": "string"}), self.analyze_impact)
        self.register("plan_tasks", "Generate task breakdown from project requirements",
                       self._s({"requirements": "string", "max_tasks?": "int"}), self.plan_tasks)
        self.register("suggest_refactor", "Suggest refactoring opportunities — long files, duplicates, complexity",
                       self._s({"path?": "string", "threshold_lines?": "int"}), self.suggest_refactor)
        self.register("manage_config", "Read/write configuration files (JSON, YAML, TOML, .env)",
                       self._s({"config_path": "string", "action": "string", "data?": "object"}),
                       self.manage_config)
        self.register("generate_docs", "Generate documentation skeleton for project modules",
                       self._s({"path?": "string", "format?": "string"}), self.generate_docs)
        self.register("organize_files", "Suggest file organization improvements",
                       self._s({"path?": "string"}), self.organize_files)

    async def analyze_structure(self, path: str = ".", max_depth: int = 5) -> dict[str, Any]:
        root = self.workspace / path if path else self.workspace
        if not root.exists():
            return {"error": f"Path not found: {path}"}

        stats: dict[str, dict[str, Any]] = {}
        total_files = 0
        total_size = 0

        for filepath in root.rglob("*"):
            if filepath.name.startswith(".") or "node_modules" in str(filepath):
                continue
            if filepath.is_file():
                ext = filepath.suffix or "no_ext"
                if ext not in stats:
                    stats[ext] = {"count": 0, "size": 0}
                size = filepath.stat().st_size
                stats[ext]["count"] += 1
                stats[ext]["size"] += size
                total_files += 1
                total_size += size

        return {"root": str(root), "total_files": total_files, "total_size_mb": round(total_size / 1024 / 1024, 2),
                "extensions": stats, "unique_extensions": len(stats)}

    async def map_dependencies(self, path: str = ".", language: str = "python") -> dict[str, Any]:
        import_patterns = {
            "python": [(r"^from\s+(\S+)\s+import", "import"), (r"^import\s+(\S+)", "import")],
            "javascript": [(r"require\s*\(\s*['\"](.+?)['\"]", "require"), (r"from\s+['\"](.+?)['\"]", "import")],
        }
        patterns = import_patterns.get(language, import_patterns["python"])
        root = self.workspace / path if path else self.workspace
        deps: dict[str, list[str]] = {}

        for filepath in root.rglob("*.py" if language == "python" else "*.{js,ts,jsx,tsx}"):
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                imports: list[str] = []
                for pattern, _ in patterns:
                    imports.extend(m.group(1) for m in re.finditer(pattern, content, re.MULTILINE))
                if imports:
                    deps[str(filepath.relative_to(self.workspace))] = imports
            except (PermissionError, OSError):
                pass

        return {"dependencies": deps, "file_count": len(deps), "language": language}

    async def analyze_impact(self, file_path: str, change_type: str = "modify") -> dict[str, Any]:
        deps = await self.map_dependencies()
        target = file_path.replace(str(self.workspace), "").lstrip("/\\")
        target_module = os.path.splitext(target.replace("/", ".").replace("\\", "."))[0]

        affected: list[str] = []
        for dep_file, imports in deps["dependencies"].items():
            for imp in imports:
                if target_module in imp or target in imp:
                    affected.append(dep_file)
                    break

        return {"target": file_path, "change_type": change_type, "affected_files": affected,
                "affected_count": len(affected), "risk": "HIGH" if len(affected) > 5 else "MEDIUM" if affected else "LOW"}

    async def plan_tasks(self, requirements: str, max_tasks: int = 10) -> dict[str, Any]:
        tasks: list[dict[str, Any]] = []
        sentences = re.split(r"[.;]\s+", requirements)
        for i, sentence in enumerate(sentences[:max_tasks]):
            sentence = sentence.strip()
            if not sentence:
                continue
            tasks.append({
                "id": i + 1,
                "title": sentence[:100],
                "priority": "high" if i < 3 else "medium",
                "estimated_hours": 2 + i % 3,
                "dependencies": [tasks[i-2]["id"]] if i >= 2 else [],
            })
        return {"tasks": tasks, "total": len(tasks), "requirements_summary": requirements[:200]}

    async def suggest_refactor(self, path: str = ".", threshold_lines: int = 300) -> dict[str, Any]:
        root = self.workspace / path if path else self.workspace
        suggestions: list[dict[str, Any]] = []

        for filepath in root.rglob("*.py"):
            try:
                content = filepath.read_text(encoding="utf-8")
                lines = content.split("\n")
                line_count = len(lines)
                if line_count > threshold_lines:
                    suggestions.append({
                        "file": str(filepath.relative_to(self.workspace)),
                        "lines": line_count,
                        "issue": "File too long",
                        "suggestion": f"Consider splitting into modules of ~{threshold_lines} lines each"
                    })
            except Exception:
                pass

        return {"suggestions": sorted(suggestions, key=lambda s: s["lines"], reverse=True),
                "count": len(suggestions), "threshold": threshold_lines}

    async def manage_config(self, config_path: str, action: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        filepath = self.workspace / config_path
        if action == "read":
            if not filepath.exists():
                return {"error": f"Config not found: {config_path}"}
            content = filepath.read_text(encoding="utf-8")
            parsed = None
            if filepath.suffix == ".json":
                parsed = json.loads(content)
            return {"path": str(filepath), "raw": content[:5000], "parsed": parsed}
        elif action == "write" and data:
            content = json.dumps(data, indent=2, ensure_ascii=False) if filepath.suffix == ".json" else str(data)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding="utf-8")
            return {"path": str(filepath), "written": True, "size": len(content)}
        return {"error": f"Unknown action: {action}"}

    async def generate_docs(self, path: str = ".", format: str = "markdown") -> dict[str, Any]:
        root = self.workspace / path if path else self.workspace
        modules: list[dict[str, Any]] = []
        for filepath in root.rglob("*.py"):
            try:
                content = filepath.read_text(encoding="utf-8")
                classes = re.findall(r"class\s+(\w+)", content)
                functions = re.findall(r"def\s+(\w+)", content)
                if classes or functions:
                    modules.append({
                        "file": str(filepath.relative_to(self.workspace)),
                        "classes": classes,
                        "functions": functions,
                    })
            except Exception:
                pass
        return {"modules": modules, "total_modules": len(modules), "format": format}

    async def organize_files(self, path: str = ".") -> dict[str, Any]:
        root = self.workspace / path if path else self.workspace
        by_type: dict[str, list[str]] = {}
        for filepath in root.rglob("*"):
            if filepath.is_file() and not filepath.name.startswith("."):
                ext = filepath.suffix or "no_ext"
                if ext not in by_type:
                    by_type[ext] = []
                by_type[ext].append(str(filepath.relative_to(self.workspace)))
        suggestions: list[str] = []
        for ext, files in by_type.items():
            if len(files) > 10 and ext != ".py":
                suggestions.append(f"Consider grouping {len(files)} {ext} files into a dedicated directory")
        return {"by_type": {k: len(v) for k, v in by_type.items()},
                "suggestions": suggestions, "total_files": sum(len(v) for v in by_type.values())}

    @staticmethod
    def _s(props: dict[str, str]) -> dict[str, Any]:
        required = [k for k in props if not k.endswith("?")]
        properties = {}
        for k, v in props.items():
            name = k.rstrip("?")
            type_map = {"string": "string", "int": "integer", "bool": "boolean", "float": "number", "array": "array", "object": "object"}
            properties[name] = {"type": type_map.get(v, "string"), "description": f"The {name} parameter"}
        return {"type": "object", "properties": properties, "required": required}
