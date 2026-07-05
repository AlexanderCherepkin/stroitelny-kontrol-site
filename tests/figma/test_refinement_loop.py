"""Unit tests for figma-agent-core/refinement_loop.py.

Loads the module via importlib because the directory name contains a hyphen.
All external module calls are injected via callbacks.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
REFINEMENT_PATH = ROOT / "figma-agent-core" / "refinement_loop.py"


def _load_refinement() -> Any:
    spec = importlib.util.spec_from_file_location("figma_refinement", str(REFINEMENT_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_refinement"] = module
    spec.loader.exec_module(module)
    return module


refinement = _load_refinement()


def test_module_loads() -> None:
    assert hasattr(refinement, "run_refinement_loop")
    assert hasattr(refinement, "RefinementReport")


def test_passes_on_first_iteration_if_visual_qa_passed(tmp_path: Path) -> None:
    ast_file = tmp_path / "layout_ast.json"
    ast_file.write_text('{"root": {"tag": "div", "classes": []}}', encoding="utf-8")

    def fake_compose(mod: Any, ast: Path, out: Path, title: Any) -> bool:
        return True

    def fake_qa(i: int, url: str, ast: Path, out: Path, ref: Any, qa_dir: Path) -> dict:
        return {"status": "passed", "diff_score": 0.01, "dom_assertions": [], "discrepancies": []}

    result = refinement.run_refinement_loop(
        page_url="http://localhost:3000",
        ast_path=str(ast_file),
        compose_output=str(tmp_path / "page.tsx"),
        report_output=str(tmp_path / "refinement_report.json"),
        on_compose=fake_compose,
        on_visual_qa=fake_qa,
    )
    assert result["status"] == "passed"
    assert result["iterations"] == 1


def test_runs_max_iterations_then_escalates(tmp_path: Path) -> None:
    ast_file = tmp_path / "layout_ast.json"
    ast_file.write_text('{"root": {"tag": "div", "classes": []}}', encoding="utf-8")

    def fake_compose(mod: Any, ast: Path, out: Path, title: Any) -> bool:
        return True

    calls = 0

    def fake_qa(i: int, url: str, ast: Path, out: Path, ref: Any, qa_dir: Path) -> dict:
        nonlocal calls
        calls += 1
        return {
            "status": "failed",
            "diff_score": 0.1,
            "dom_assertions": [],
            "discrepancies": ["padding mismatch"],
        }

    result = refinement.run_refinement_loop(
        page_url="http://localhost:3000",
        ast_path=str(ast_file),
        compose_output=str(tmp_path / "page.tsx"),
        max_iterations=2,
        report_output=str(tmp_path / "refinement_report.json"),
        on_compose=fake_compose,
        on_visual_qa=fake_qa,
    )
    assert result["status"] == "needs_human"
    assert result["iterations"] == 2
    assert "max iterations" in result["escalation_reason"].lower()
    assert calls == 2


def test_fails_fast_when_compose_fails(tmp_path: Path) -> None:
    ast_file = tmp_path / "layout_ast.json"
    ast_file.write_text('{"root": {"tag": "div", "classes": []}}', encoding="utf-8")

    def fake_compose(mod: Any, ast: Path, out: Path, title: Any) -> bool:
        return False

    result = refinement.run_refinement_loop(
        page_url="http://localhost:3000",
        ast_path=str(ast_file),
        compose_output=str(tmp_path / "page.tsx"),
        report_output=str(tmp_path / "refinement_report.json"),
        on_compose=fake_compose,
        on_visual_qa=lambda *args: {"status": "passed"},
    )
    assert result["status"] == "failed"
    assert "compose" in result["escalation_reason"].lower()


def test_blocked_visual_qa_triggers_refinement_then_human(tmp_path: Path) -> None:
    ast_file = tmp_path / "layout_ast.json"
    ast_file.write_text('{"root": {"tag": "div", "classes": []}}', encoding="utf-8")

    def fake_compose(mod: Any, ast: Path, out: Path, title: Any) -> bool:
        return True

    def fake_qa(i: int, url: str, ast: Path, out: Path, ref: Any, qa_dir: Path) -> dict:
        return {"status": "blocked", "discrepancies": ["Playwright not installed"]}

    result = refinement.run_refinement_loop(
        page_url="http://evil.example.com",
        ast_path=str(ast_file),
        compose_output=str(tmp_path / "page.tsx"),
        max_iterations=1,
        report_output=str(tmp_path / "refinement_report.json"),
        on_compose=fake_compose,
        on_visual_qa=fake_qa,
    )
    assert result["status"] == "needs_human"
    assert result["iterations"] == 1


def test_applies_deterministic_adjustments(tmp_path: Path) -> None:
    ast_file = tmp_path / "layout_ast.json"
    ast_file.write_text('{"root": {"tag": "div", "classes": []}}', encoding="utf-8")

    def fake_compose(mod: Any, ast: Path, out: Path, title: Any) -> bool:
        return True

    iterations = []

    def fake_qa(i: int, url: str, ast: Path, out: Path, ref: Any, qa_dir: Path) -> dict:
        iterations.append(i)
        if i == 1:
            return {
                "status": "failed",
                "diff_score": 0.12,
                "dom_assertions": [],
                "discrepancies": ["padding mismatch", "font size mismatch"],
            }
        return {"status": "passed", "diff_score": 0.02, "dom_assertions": [], "discrepancies": []}

    def fake_adjust(ast: dict, report: dict) -> list:
        ast["root"]["classes"].append("p-4")
        return [{"type": "padding", "reason": "padding mismatch"}]

    result = refinement.run_refinement_loop(
        page_url="http://localhost:3000",
        ast_path=str(ast_file),
        compose_output=str(tmp_path / "page.tsx"),
        max_iterations=3,
        report_output=str(tmp_path / "refinement_report.json"),
        on_compose=fake_compose,
        on_visual_qa=fake_qa,
        on_adjust=fake_adjust,
    )
    assert result["status"] == "passed"
    assert result["iterations"] == 2
    assert len(result["adjustments"]) >= 1
    assert result["adjustments"][0]["type"] == "padding"
    assert iterations == [1, 2]


def test_missing_ast_file_blocks_immediately(tmp_path: Path) -> None:
    result = refinement.run_refinement_loop(
        page_url="http://localhost:3000",
        ast_path=str(tmp_path / "missing.json"),
        compose_output=str(tmp_path / "page.tsx"),
        report_output=str(tmp_path / "refinement_report.json"),
    )
    assert result["status"] == "blocked"
    assert result["iterations"] == 0
    assert Path(tmp_path / "refinement_report.json").exists()


def test_dom_assertion_failure_triggers_refinement(tmp_path: Path) -> None:
    ast_file = tmp_path / "layout_ast.json"
    ast_file.write_text('{"root": {"tag": "div", "classes": []}}', encoding="utf-8")

    def fake_compose(mod: Any, ast: Path, out: Path, title: Any) -> bool:
        return True

    def fake_qa(i: int, url: str, ast: Path, out: Path, ref: Any, qa_dir: Path) -> dict:
        return {
            "status": "passed",
            "diff_score": 0.0,
            "dom_assertions": [
                {
                    "selector": "h1",
                    "expected": {"selector": "h1", "expected_count": 1},
                    "actual": {"count": 0},
                    "passed": False,
                    "discrepancies": ["expected 1 elements, found 0"],
                }
            ],
            "discrepancies": [],
        }

    result = refinement.run_refinement_loop(
        page_url="http://localhost:3000",
        ast_path=str(ast_file),
        compose_output=str(tmp_path / "page.tsx"),
        max_iterations=1,
        report_output=str(tmp_path / "refinement_report.json"),
        on_compose=fake_compose,
        on_visual_qa=fake_qa,
    )
    assert result["status"] == "needs_human"
    assert any(a["type"] == "add_node" for a in result["adjustments"])


def test_layout_checks_trigger_refinement(tmp_path: Path) -> None:
    ast_file = tmp_path / "layout_ast.json"
    ast_file.write_text(
        '{"root": {"tag": "div", "figma_id": "1:1", "classes": ["h-full"], "children": []}}',
        encoding="utf-8",
    )

    def fake_compose(mod: Any, ast: Path, out: Path, title: Any) -> bool:
        return True

    def fake_qa(i: int, url: str, ast: Path, out: Path, ref: Any, qa_dir: Path) -> dict:
        return {
            "status": "failed",
            "diff_score": 0.01,
            "dom_assertions": [],
            "layout_checks": [
                {
                    "type": "overflow",
                    "passed": False,
                    "overflow_y": True,
                    "page": {"figma_id": "1:1"},
                }
            ],
            "discrepancies": [],
        }

    result = refinement.run_refinement_loop(
        page_url="http://localhost:3000",
        ast_path=str(ast_file),
        compose_output=str(tmp_path / "page.tsx"),
        max_iterations=1,
        report_output=str(tmp_path / "refinement_report.json"),
        on_compose=fake_compose,
        on_visual_qa=fake_qa,
    )
    assert result["status"] == "needs_human"
    adjustment = result["adjustments"][0]
    assert adjustment["type"] == "overflow_fix"
    saved = json.loads(ast_file.read_text(encoding="utf-8"))
    assert "overflow-hidden" in saved["root"]["classes"]
    assert "h-full" not in saved["root"]["classes"]


def test_bbox_mismatch_applies_exact_size(tmp_path: Path) -> None:
    ast_file = tmp_path / "layout_ast.json"
    ast_file.write_text(
        '{"root": {"tag": "section", "figma_id": "1:1", "classes": ["w-full", "h-auto"], "children": []}}',
        encoding="utf-8",
    )

    def fake_compose(mod: Any, ast: Path, out: Path, title: Any) -> bool:
        return True

    def fake_qa(i: int, url: str, ast: Path, out: Path, ref: Any, qa_dir: Path) -> dict:
        return {
            "status": "failed",
            "diff_score": 0.12,
            "dom_assertions": [],
            "layout_checks": [
                {
                    "type": "bbox_mismatch",
                    "passed": False,
                    "page": {"figma_id": "1:1", "x": 0, "y": 0, "width": 300, "height": 120},
                    "figma": {"id": "1:1", "x": 0, "y": 0, "width": 320, "height": 80},
                    "delta_x": 0,
                    "delta_y": 0,
                    "delta_width": -20,
                    "delta_height": 40,
                    "discrepancy": "size mismatch",
                }
            ],
            "discrepancies": [],
        }

    result = refinement.run_refinement_loop(
        page_url="http://localhost:3000",
        ast_path=str(ast_file),
        compose_output=str(tmp_path / "page.tsx"),
        max_iterations=1,
        report_output=str(tmp_path / "refinement_report.json"),
        on_compose=fake_compose,
        on_visual_qa=fake_qa,
    )
    assert result["status"] == "needs_human"
    saved = json.loads(ast_file.read_text(encoding="utf-8"))
    classes = saved["root"]["classes"]
    assert "w-[320px]" in classes
    assert "h-[80px]" in classes
    assert "w-full" not in classes


def test_snug_text_fix_adjusts_width_when_fixed_width_present(tmp_path: Path) -> None:
    ast_file = tmp_path / "layout_ast.json"
    ast_file.write_text(
        '{"root": {"tag": "section", "children": [{"tag": "p", "figma_id": "2:1", "classes": ["w-[120px]"]}]}}',
        encoding="utf-8",
    )

    def fake_compose(mod: Any, ast: Path, out: Path, title: Any) -> bool:
        return True

    def fake_qa(i: int, url: str, ast: Path, out: Path, ref: Any, qa_dir: Path) -> dict:
        return {
            "status": "failed",
            "diff_score": 0.05,
            "dom_assertions": [],
            "layout_checks": [
                {
                    "type": "snug_text",
                    "passed": False,
                    "figma_id": "2:1",
                    "figma_width": 100,
                    "page_width": 140,
                    "delta_width": 40,
                    "discrepancy": "Rendered text width exceeds Figma text bbox",
                }
            ],
            "discrepancies": [],
        }

    result = refinement.run_refinement_loop(
        page_url="http://localhost:3000",
        ast_path=str(ast_file),
        compose_output=str(tmp_path / "page.tsx"),
        max_iterations=1,
        report_output=str(tmp_path / "refinement_report.json"),
        on_compose=fake_compose,
        on_visual_qa=fake_qa,
    )
    assert result["status"] == "needs_human"
    saved = json.loads(ast_file.read_text(encoding="utf-8"))
    classes = saved["root"]["children"][0]["classes"]
    assert "w-[100px]" in classes
    assert "min-w-0" not in classes


def test_snug_text_fix_adds_min_w_0_for_single_line_flex_label(tmp_path: Path) -> None:
    ast_file = tmp_path / "layout_ast.json"
    ast_file.write_text(
        '{"root": {"tag": "section", "classes": ["flex", "flex-row"], "children": [{"tag": "p", "figma_id": "2:1", "classes": ["flex", "flex-1"]}]}}',
        encoding="utf-8",
    )

    def fake_compose(mod: Any, ast: Path, out: Path, title: Any) -> bool:
        return True

    def fake_qa(i: int, url: str, ast: Path, out: Path, ref: Any, qa_dir: Path) -> dict:
        return {
            "status": "failed",
            "diff_score": 0.05,
            "dom_assertions": [],
            "layout_checks": [
                {
                    "type": "snug_text",
                    "passed": False,
                    "figma_id": "2:1",
                    "figma_width": 100,
                    "page_width": 140,
                    "delta_width": 40,
                    "discrepancy": "Rendered text width exceeds Figma text bbox",
                }
            ],
            "discrepancies": [],
        }

    result = refinement.run_refinement_loop(
        page_url="http://localhost:3000",
        ast_path=str(ast_file),
        compose_output=str(tmp_path / "page.tsx"),
        max_iterations=1,
        report_output=str(tmp_path / "refinement_report.json"),
        on_compose=fake_compose,
        on_visual_qa=fake_qa,
    )
    assert result["status"] == "needs_human"
    saved = json.loads(ast_file.read_text(encoding="utf-8"))
    classes = saved["root"]["children"][0]["classes"]
    assert "whitespace-nowrap" in classes
    assert "min-w-0" in classes


def test_convergence_guard_escalates_when_score_stagnates(tmp_path: Path) -> None:
    ast_file = tmp_path / "layout_ast.json"
    ast_file.write_text('{"root": {"tag": "div", "figma_id": "1:1", "classes": [], "children": []}}', encoding="utf-8")

    def fake_compose(mod: Any, ast: Path, out: Path, title: Any) -> bool:
        return True

    def fake_qa(i: int, url: str, ast: Path, out: Path, ref: Any, qa_dir: Path) -> dict:
        return {
            "status": "failed",
            "diff_score": 0.15,
            "dom_assertions": [],
            "layout_checks": [
                {
                    "type": "bbox_mismatch",
                    "passed": False,
                    "page": {"figma_id": "1:1", "width": 100, "height": 100},
                    "figma": {"id": "1:1", "width": 120, "height": 120},
                    "delta_width": -20,
                    "delta_height": -20,
                }
            ],
            "discrepancies": [],
        }

    result = refinement.run_refinement_loop(
        page_url="http://localhost:3000",
        ast_path=str(ast_file),
        compose_output=str(tmp_path / "page.tsx"),
        max_iterations=5,
        report_output=str(tmp_path / "refinement_report.json"),
        on_compose=fake_compose,
        on_visual_qa=fake_qa,
    )
    assert result["status"] == "needs_human"
    assert "did not improve" in result["escalation_reason"].lower()
    assert result["iterations"] == 3


def test_font_mismatch_adjusts_text_classes() -> None:
    ast = {
        "root": {
            "tag": "p",
            "figma_id": "10:1",
            "classes": ["text-base", "font-normal"],
            "children": [],
        }
    }
    report = {
        "layout_checks": [
            {
                "type": "font_mismatch",
                "passed": False,
                "page": {"figma_id": "10:1"},
                "figma": {
                    "font_size": 18,
                    "font_weight": 700,
                    "line_height_px": 27,
                    "letter_spacing": 1,
                },
                "mismatches": ["size", "weight", "line_height", "letter_spacing"],
            }
        ]
    }
    adjustments = refinement._apply_layout_adjustments(ast, report)
    classes = ast["root"]["classes"]
    assert "text-[18px]" in classes
    assert "font-[700]" in classes
    assert "leading-[1.5]" in classes
    assert "tracking-[1px]" in classes
    assert any(a["type"] == "font_fix" for a in adjustments)


def test_snug_text_adds_max_width() -> None:
    ast = {
        "root": {
            "tag": "span",
            "figma_id": "20:1",
            "classes": ["text-sm"],
            "children": [],
        }
    }
    report = {
        "layout_checks": [
            {
                "type": "snug_text",
                "passed": False,
                "figma_id": "20:1",
                "figma_width": 142,
                "page_width": 180,
                "delta_width": 38,
            }
        ]
    }
    adjustments = refinement._apply_layout_adjustments(ast, report)
    classes = ast["root"]["classes"]
    assert "max-w-[142px]" in classes
    assert any(a["type"] == "snug_text_fix" for a in adjustments)


def test_snug_text_prefers_whitespace_nowrap_for_flex_row() -> None:
    ast = {
        "root": {
            "tag": "span",
            "figma_id": "21:1",
            "classes": ["flex", "flex-row", "text-sm"],
            "children": [],
        }
    }
    report = {
        "layout_checks": [
            {
                "type": "snug_text",
                "passed": False,
                "figma_id": "21:1",
                "figma_width": 92,
                "page_width": 130,
                "delta_width": 38,
            }
        ]
    }
    adjustments = refinement._apply_layout_adjustments(ast, report)
    classes = ast["root"]["classes"]
    assert "whitespace-nowrap" in classes
    assert "max-w-[92px]" not in classes


