"""Unit tests for figma-agent-core/compliance_checker.py.

Loads the module via importlib because the directory name contains a hyphen.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
COMPLIANCE_PATH = ROOT / "figma-agent-core" / "compliance_checker.py"


def _load_compliance() -> Any:
    spec = importlib.util.spec_from_file_location("figma_compliance", str(COMPLIANCE_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_compliance"] = module
    spec.loader.exec_module(module)
    return module


compliance = _load_compliance()


def test_module_loads() -> None:
    assert hasattr(compliance, "run_compliance_check")
    assert hasattr(compliance, "check_file")


def test_passes_clean_file(tmp_path: Path) -> None:
    file = tmp_path / "page.tsx"
    file.write_text('export default function Page() { return <h1>Hello</h1>; }\n', encoding="utf-8")
    result = compliance.run_compliance_check(
        code_paths=[str(file)],
        workspace_root=str(tmp_path),
        rules_path=str(tmp_path / "project_rules.md"),
    )
    assert result["passed"] is True
    assert result["summary"]["total_violations"] == 0
    assert result["summary"]["total_placeholders"] == 0


def test_detects_lorem_ipsum(tmp_path: Path) -> None:
    file = tmp_path / "page.tsx"
    file.write_text('export default function Page() { return <p>Lorem ipsum dolor sit amet.</p>; }\n', encoding="utf-8")
    result = compliance.run_compliance_check(
        code_paths=[str(file)],
        workspace_root=str(tmp_path),
        rules_path=str(tmp_path / "project_rules.md"),
    )
    assert result["passed"] is False
    assert result["summary"]["total_placeholders"] == 1
    assert "lorem ipsum" in result["placeholders"][0]["match"].lower()


def test_detects_todo_placeholder(tmp_path: Path) -> None:
    file = tmp_path / "page.tsx"
    file.write_text('export default function Page() { return <p>TODO: add content</p>; }\n', encoding="utf-8")
    result = compliance.run_compliance_check(
        code_paths=[str(file)],
        workspace_root=str(tmp_path),
        rules_path=str(tmp_path / "project_rules.md"),
    )
    assert result["passed"] is False
    assert result["summary"]["total_placeholders"] == 1


def test_detects_dangerous_eval(tmp_path: Path) -> None:
    file = tmp_path / "page.tsx"
    file.write_text('const x = eval("window.location");\n', encoding="utf-8")
    result = compliance.run_compliance_check(
        code_paths=[str(file)],
        workspace_root=str(tmp_path),
        rules_path=str(tmp_path / "project_rules.md"),
    )
    assert result["passed"] is False
    assert any(v["message"] == "eval() call detected" for v in result["violations"])


def test_detects_hardcoded_secret(tmp_path: Path) -> None:
    file = tmp_path / "page.tsx"
    file.write_text('const token = "ghp_000000000000000000000000000000000000";\n', encoding="utf-8")
    result = compliance.run_compliance_check(
        code_paths=[str(file)],
        workspace_root=str(tmp_path),
        rules_path=str(tmp_path / "project_rules.md"),
    )
    assert result["passed"] is False
    assert any("GitHub personal access token" in v["message"] for v in result["violations"])


def test_blocks_path_traversal_import(tmp_path: Path) -> None:
    file = tmp_path / "page.tsx"
    file.write_text('import Foo from "../../secret";\n', encoding="utf-8")
    result = compliance.run_compliance_check(
        code_paths=[str(file)],
        workspace_root=str(tmp_path),
        rules_path=str(tmp_path / "project_rules.md"),
    )
    assert result["passed"] is False
    assert any("path traversal" in v["message"].lower() for v in result["violations"])


def test_blocks_file_outside_workspace(tmp_path: Path) -> None:
    outside = tmp_path / ".." / "outside_page.tsx"
    result = compliance.run_compliance_check(
        code_paths=[str(outside)],
        workspace_root=str(tmp_path),
        rules_path=str(tmp_path / "project_rules.md"),
    )
    assert result["passed"] is False
    assert any(v["rule"] == "workspace boundary" for v in result["violations"])


def test_project_rules_no_comments_flag(tmp_path: Path) -> None:
    rules = tmp_path / "project_rules.md"
    rules.write_text("- **No comments** unless the WHY is non-obvious.\n", encoding="utf-8")
    file = tmp_path / "page.tsx"
    file.write_text('export default function Page() {\n  // this is a generic comment\n  return <h1>Hi</h1>;\n}\n', encoding="utf-8")
    result = compliance.run_compliance_check(
        code_paths=[str(file)],
        workspace_root=str(tmp_path),
        rules_path=str(rules),
    )
    assert result["passed"] is False
    assert any("comment may not explain WHY" in v["message"] for v in result["violations"])


def test_project_rules_allows_why_comment(tmp_path: Path) -> None:
    rules = tmp_path / "project_rules.md"
    rules.write_text("- **No comments** unless the WHY is non-obvious.\n", encoding="utf-8")
    file = tmp_path / "page.tsx"
    file.write_text('export default function Page() {\n  // because Safari needs fallback\n  return <h1>Hi</h1>;\n}\n', encoding="utf-8")
    result = compliance.run_compliance_check(
        code_paths=[str(file)],
        workspace_root=str(tmp_path),
        rules_path=str(rules),
    )
    assert result["passed"] is True
    assert all("comment may not explain WHY" not in v["message"] for v in result["violations"])


def test_custom_placeholder_pattern(tmp_path: Path) -> None:
    file = tmp_path / "page.tsx"
    file.write_text('export default function Page() { return <p>Acme placeholder brand</p>; }\n', encoding="utf-8")
    result = compliance.run_compliance_check(
        code_paths=[str(file)],
        workspace_root=str(tmp_path),
        rules_path=str(tmp_path / "project_rules.md"),
        placeholder_patterns=["acme placeholder brand"],
    )
    assert result["passed"] is False
    assert result["summary"]["total_placeholders"] == 1


def test_report_written_to_output_path(tmp_path: Path) -> None:
    file = tmp_path / "page.tsx"
    file.write_text('export default function Page() { return <h1>Hello</h1>; }\n', encoding="utf-8")
    output = tmp_path / "compliance_report.json"
    result = compliance.run_compliance_check(
        code_paths=[str(file)],
        workspace_root=str(tmp_path),
        rules_path=str(tmp_path / "project_rules.md"),
        output_path=str(output),
    )
    assert output.exists()
    assert output.read_text(encoding="utf-8").startswith("{")
    assert result["passed"] is True
