from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from .base import MCPServer


class RuntestMCPServer(MCPServer):
    """MCP server for tools_runtest — test execution pipeline (framework-dispatch)."""

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="tools_runtest", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()
        self._test_cache: dict[str, dict[str, Any]] = {}

        self.register("discover_tests", "Discover test files and test functions in project",
                       self._s({"path?": "string", "framework?": "string"}),
                       self.discover_tests)
        self.register("plan_execution", "Plan test execution order and priority",
                       self._s({"tests": "array", "strategy?": "string"}), self.plan_execution)
        self.register("optimize_suite", "Optimize test suite — parallelize, prioritize, deduplicate",
                       self._s({"tests": "array", "max_parallel?": "int"}), self.optimize_suite)
        self.register("execute_test", "Execute a single test and capture result",
                       self._s({"test_file": "string", "test_name?": "string",
                                "framework?": "string", "timeout_ms?": "int"}),
                       self.execute_test)
        self.register("collect_coverage", "Collect code coverage data after test run",
                       self._s({"source_path": "string", "test_results": "array"}),
                       self.collect_coverage)
        self.register("analyze_failure", "Analyze test failure — extract error, traceback, suggest fix",
                       self._s({"test_name": "string", "stdout": "string", "stderr": "string"}),
                       self.analyze_failure)
        self.register("detect_flaky", "Detect flaky tests from multiple runs",
                       self._s({"test_name": "string", "run_results": "array"}), self.detect_flaky)
        self.register("generate_report", "Generate test run report with stats and trends",
                       self._s({"results": "array", "format?": "string"}), self.generate_report)

    async def discover_tests(self, path: str = ".", framework: str = "auto") -> dict[str, Any]:
        search_path = self.workspace / path if path else self.workspace
        discovered: list[dict[str, Any]] = []

        test_patterns = {
            "python": (r"(test_|_test\.py$)", r"def (test_\w+)"),
            "javascript": (r"(\.test\.|\.spec\.)(js|ts|jsx|tsx)$", r"(test|it)\s*\(\s*['\"](.+?)['\"]"),
            "go": (r"_test\.go$", r"func (Test\w+)"),
        }

        skip_dirs = {"node_modules", ".venv", "venv", "__pycache__", ".git", "dist", "build", ".tox", ".pytest_cache"}

        for filepath in search_path.rglob("*"):
            if not filepath.is_file():
                continue
            if any(part in skip_dirs for part in filepath.parts):
                continue
            fname = str(filepath)
            for lang, (file_pattern, func_pattern) in test_patterns.items():
                if re.search(file_pattern, fname):
                    try:
                        content = filepath.read_text(encoding="utf-8", errors="replace")
                        funcs = re.findall(func_pattern, content)
                        for func in funcs:
                            name = func if isinstance(func, str) else (func[1] if len(func) > 1 else func[0])
                            discovered.append({
                                "file": str(filepath), "test_name": name,
                                "framework": lang, "language": lang,
                            })
                    except (PermissionError, OSError):
                        pass

        return {"tests": discovered, "count": len(discovered),
                "path": str(search_path), "framework": framework}

    async def plan_execution(self, tests: list[dict[str, Any]], strategy: str = "balanced") -> dict[str, Any]:
        plan = {"strategy": strategy, "phases": []}
        if strategy == "fast_fail":
            plan["phases"] = [{"name": "critical", "tests": [t for t in tests if "critical" in str(t).lower()]},
                              {"name": "remaining", "tests": tests}]
        elif strategy == "balanced":
            mid = len(tests) // 2
            plan["phases"] = [{"name": "phase_1", "tests": tests[:mid]},
                              {"name": "phase_2", "tests": tests[mid:]}]
        else:
            plan["phases"] = [{"name": "all", "tests": tests}]
        return {"plan": plan, "total_tests": len(tests), "phases_count": len(plan["phases"])}

    async def optimize_suite(self, tests: list[dict[str, Any]], max_parallel: int = 4) -> dict[str, Any]:
        files = list(set(t.get("file", "") for t in tests))
        parallel_groups = [files[i:i + max_parallel] for i in range(0, len(files), max_parallel)]
        return {"tests": tests, "files": files, "parallel_groups": parallel_groups,
                "max_parallel": max_parallel, "file_count": len(files)}

    async def execute_test(self, test_file: str, test_name: str = "",
                           framework: str = "pytest", timeout_ms: int = 60000) -> dict[str, Any]:
        filepath = self.workspace / test_file
        if not filepath.exists():
            return {"error": f"Test file not found: {test_file}"}

        t0 = time.perf_counter()

        if framework == "pytest":
            cmd = ["python", "-m", "pytest", str(filepath), "-v"]
            if test_name:
                cmd.append(f"-k {test_name}")
        elif framework == "jest":
            cmd = ["npx", "jest", str(filepath)]
            if test_name:
                cmd.extend(["-t", test_name])
        elif framework == "go":
            cmd = ["go", "test", str(filepath)]
            if test_name:
                cmd.extend(["-run", test_name])
        else:
            cmd = ["python", "-m", "pytest", str(filepath), "-v"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=timeout_ms / 1000, cwd=str(self.workspace))
            latency = (time.perf_counter() - t0) * 1000
            passed = result.returncode == 0
            return {
                "test_file": test_file, "test_name": test_name,
                "passed": passed, "exit_code": result.returncode,
                "stdout": result.stdout[:20000], "stderr": result.stderr[:10000],
                "latency_ms": latency,
            }
        except subprocess.TimeoutExpired:
            return {"test_file": test_file, "test_name": test_name,
                    "passed": False, "error": "timeout", "latency_ms": timeout_ms}

    async def collect_coverage(self, source_path: str, test_results: list[dict[str, Any]]) -> dict[str, Any]:
        return {"source_path": source_path, "note": "Coverage collection requires coverage tool (coverage.py/pytest-cov)",
                "recommendation": "Run: python -m pytest --cov=src --cov-report=json"}

    async def analyze_failure(self, test_name: str, stdout: str, stderr: str) -> dict[str, Any]:
        combined = stdout + "\n" + stderr
        analysis = {"test": test_name, "issues": [], "suggestions": []}

        if "AssertionError" in combined:
            analysis["issues"].append({"type": "assertion", "detail": "Expected value does not match actual"})
            analysis["suggestions"].append("Check assertion values and types")
        if "ImportError" in combined or "ModuleNotFoundError" in combined:
            analysis["issues"].append({"type": "import", "detail": "Missing dependency"})
            analysis["suggestions"].append("Install missing package or check import path")
        if "AttributeError" in combined:
            analysis["issues"].append({"type": "attribute", "detail": "Object has no such attribute"})
            analysis["suggestions"].append("Check object type and available attributes")
        if "Timeout" in combined or "timed out" in combined:
            analysis["issues"].append({"type": "timeout", "detail": "Test exceeded time limit"})
            analysis["suggestions"].append("Increase timeout or optimize test performance")
        if "connection refused" in combined.lower():
            analysis["issues"].append({"type": "network", "detail": "Cannot connect to service"})
            analysis["suggestions"].append("Ensure required services are running (DB, API, etc.)")

        if not analysis["issues"]:
            analysis["issues"].append({"type": "unknown", "detail": "Could not classify the failure"})

        return analysis

    async def detect_flaky(self, test_name: str, run_results: list[dict[str, Any]]) -> dict[str, Any]:
        passes = sum(1 for r in run_results if r.get("passed"))
        fails = sum(1 for r in run_results if not r.get("passed"))
        total = len(run_results)
        flaky_score = 0.0
        if total >= 2:
            transitions = sum(1 for i in range(1, total)
                              if run_results[i].get("passed") != run_results[i-1].get("passed"))
            flaky_score = transitions / (total - 1) if total > 1 else 0

        is_flaky = flaky_score > 0.3 and passes > 0 and fails > 0
        return {"test_name": test_name, "total_runs": total, "passes": passes, "fails": fails,
                "flaky_score": flaky_score, "is_flaky": is_flaky,
                "verdict": "FLAKY" if is_flaky else "STABLE" if passes == total else "BROKEN" if fails == total else "UNSTABLE"}

    async def generate_report(self, results: list[dict[str, Any]], format: str = "summary") -> dict[str, Any]:
        total = len(results)
        passed = sum(1 for r in results if r.get("passed"))
        failed = total - passed
        latencies = [r.get("latency_ms", 0) for r in results if r.get("latency_ms")]

        return {
            "total": total, "passed": passed, "failed": failed,
            "pass_rate": f"{passed/total*100:.1f}%" if total > 0 else "0%",
            "avg_latency_ms": f"{sum(latencies)/len(latencies):.0f}" if latencies else "N/A",
            "failed_tests": [r.get("test_name", r.get("test_file", "unknown")) for r in results if not r.get("passed")],
            "format": format,
        }

    @staticmethod
    def _s(props: dict[str, str]) -> dict[str, Any]:
        required = [k for k in props if not k.endswith("?")]
        properties = {}
        for k, v in props.items():
            name = k.rstrip("?")
            type_map = {"string": "string", "int": "integer", "bool": "boolean", "float": "number", "array": "array"}
            properties[name] = {"type": type_map.get(v, "string"), "description": f"The {name} parameter"}
        return {"type": "object", "properties": properties, "required": required}
