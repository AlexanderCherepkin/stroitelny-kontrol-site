"""Unit tests for figma-agent-core/precise_mode_auditor.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
AUDITOR_PATH = ROOT / "figma-agent-core" / "precise_mode_auditor.py"


def _load_auditor_module() -> Any:
    spec = importlib.util.spec_from_file_location("figma_precise_mode_auditor", str(AUDITOR_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_precise_mode_auditor"] = module
    spec.loader.exec_module(module)
    return module


auditor_module = _load_auditor_module()


def _make_node(node_id: str, name: str, node_type: str, **kwargs: Any) -> dict:
    return {"id": node_id, "name": name, "type": node_type, **kwargs}


def test_ready_design_returns_ready() -> None:
    root = _make_node(
        "1:1",
        "Desktop",
        "FRAME",
        box={"x": 0, "y": 0, "width": 1440, "height": 900},
        layoutMode="VERTICAL",
        children=[
            _make_node(
                "2:1",
                "Hero",
                "FRAME",
                layoutMode="VERTICAL",
                children=[],
                box={"x": 0, "y": 0, "width": 1440, "height": 400},
            ),
            _make_node(
                "3:1",
                "Footer",
                "FRAME",
                layoutMode="VERTICAL",
                children=[],
                box={"x": 0, "y": 400, "width": 1440, "height": 100},
            ),
            _make_node(
                "4:1",
                "Button",
                "COMPONENT",
                box={"x": 100, "y": 500, "width": 120, "height": 40},
            ),
        ],
    )
    auditor = auditor_module.PreciseModeAuditor(root)
    result = auditor.audit()
    assert result["status"] == "ready"
    assert result["next_phase_hint"] == "continue"
    assert result["score"] >= 0.90
    assert result["metrics"]["threshold_ready"] == 0.90
    assert result["metrics"]["threshold_cleanup"] == 0.80
    failed_checks = [c["check_id"] for c in result["checks"] if not c["passed"]]
    assert failed_checks == []


def test_missing_auto_layout_is_not_ready() -> None:
    root = _make_node(
        "1:1",
        "Desktop",
        "FRAME",
        box={"x": 0, "y": 0, "width": 1440, "height": 900},
        children=[
            _make_node("2:1", "Hero", "FRAME", children=[], box={"x": 0, "y": 0, "width": 1440, "height": 400}),
        ],
    )
    auditor = auditor_module.PreciseModeAuditor(root)
    result = auditor.audit()
    assert result["status"] == "not_ready"
    assert result["next_phase_hint"] == "halt_for_cleanup"
    auto_layout = next(c for c in result["checks"] if c["check_id"] == "auto_layout_coverage")
    assert not auto_layout["passed"]


def test_loose_text_is_needs_cleanup() -> None:
    root = _make_node(
        "1:1",
        "Frame 1",
        "FRAME",
        box={"x": 0, "y": 0, "width": 1440, "height": 900},
        layoutMode="VERTICAL",
        children=[
            _make_node(
                "2:1",
                "Loose",
                "TEXT",
                characters="Hi",
                fontSize=16,
                box={"x": 0, "y": 0, "width": 400, "height": 80},
            ),
            _make_node("3:1", "Tight1", "TEXT", characters="A", fontSize=16, box={"x": 0, "y": 100, "width": 20, "height": 18}),
            _make_node("4:1", "Tight2", "TEXT", characters="B", fontSize=16, box={"x": 0, "y": 130, "width": 20, "height": 18}),
            _make_node("5:1", "Tight3", "TEXT", characters="C", fontSize=16, box={"x": 0, "y": 160, "width": 20, "height": 18}),
            _make_node("6:1", "Translucent", "RECTANGLE", opacity=0.8, box={"x": 0, "y": 200, "width": 100, "height": 100}),
        ],
    )
    auditor = auditor_module.PreciseModeAuditor(root)
    result = auditor.audit()
    assert result["status"] == "needs_cleanup"
    assert result["next_phase_hint"] == "warn_and_continue"
    snug = next(c for c in result["checks"] if c["check_id"] == "snug_text")
    assert not snug["passed"]
    assert snug["severity"] == "warning"


def test_viewport_mismatch_is_warning() -> None:
    root = _make_node(
        "1:1",
        "Mobile",
        "FRAME",
        box={"x": 0, "y": 0, "width": 3200, "height": 2000},
        layoutMode="VERTICAL",
    )
    auditor = auditor_module.PreciseModeAuditor(root)
    result = auditor.audit()
    viewport = next(c for c in result["checks"] if c["check_id"] == "viewport_realism")
    assert not viewport["passed"]
    assert viewport["severity"] == "warning"
    assert result["score"] < 1.0


def test_critical_issue_overrides_score() -> None:
    children = [_make_node(f"2:{i}", f"Box{i}", "RECTANGLE", box={"x": i * 5, "y": 0, "width": 50, "height": 50}) for i in range(12)]
    root = _make_node(
        "1:1",
        "Frame 1",
        "FRAME",
        box={"x": 0, "y": 0, "width": 1440, "height": 900},
        layoutMode="VERTICAL",
        children=children,
    )
    auditor = auditor_module.PreciseModeAuditor(root)
    result = auditor.audit()
    assert result["status"] == "not_ready"
    overlaps = next(c for c in result["checks"] if c["check_id"] == "overlap_intersection")
    assert not overlaps["passed"]
    assert overlaps["severity"] == "critical"


def test_audit_returns_expected_report_keys() -> None:
    root = _make_node("1:1", "Desktop", "FRAME", box={"x": 0, "y": 0, "width": 1440, "height": 900}, layoutMode="VERTICAL")
    auditor = auditor_module.PreciseModeAuditor(root)
    result = auditor.audit()
    assert set(result.keys()) >= {
        "score",
        "status",
        "target_viewport",
        "checks",
        "auto_fixable",
        "requires_designer",
        "next_phase_hint",
        "metrics",
    }
    assert "threshold_ready" in result["metrics"]
    assert "threshold_cleanup" in result["metrics"]
    assert result["metrics"]["total_checks"] == 8
    assert isinstance(result["checks"], list)
    assert len(result["checks"]) == 8


def test_auto_width_text_is_considered_snug() -> None:
    root = _make_node(
        "1:1",
        "Desktop",
        "FRAME",
        box={"x": 0, "y": 0, "width": 1440, "height": 900},
        layoutMode="VERTICAL",
        children=[
            _make_node(
                "2:1",
                "Loose",
                "TEXT",
                characters="Hi",
                fontSize=16,
                textAutoResize="WIDTH_AND_HEIGHT",
                box={"x": 0, "y": 0, "width": 400, "height": 80},
            ),
        ],
    )
    auditor = auditor_module.PreciseModeAuditor(root)
    result = auditor.audit()
    snug = next(c for c in result["checks"] if c["check_id"] == "snug_text")
    assert snug["passed"]


def test_content_box_within_tolerance_is_snug() -> None:
    root = _make_node(
        "1:1",
        "Desktop",
        "FRAME",
        box={"x": 0, "y": 0, "width": 1440, "height": 900},
        layoutMode="VERTICAL",
        children=[
            _make_node(
                "2:1",
                "Tight",
                "TEXT",
                characters="Hi",
                fontSize=16,
                textAutoResize="NONE",
                box={"x": 0, "y": 0, "width": 34, "height": 22},
                boundingBox={"x": 0, "y": 0, "width": 30, "height": 18},
            ),
        ],
    )
    auditor = auditor_module.PreciseModeAuditor(root)
    result = auditor.audit()
    snug = next(c for c in result["checks"] if c["check_id"] == "snug_text")
    assert snug["passed"]


def test_fixed_width_text_with_loose_content_box_is_flagged() -> None:
    root = _make_node(
        "1:1",
        "Desktop",
        "FRAME",
        box={"x": 0, "y": 0, "width": 1440, "height": 900},
        layoutMode="VERTICAL",
        children=[
            _make_node(
                "2:1",
                "Loose",
                "TEXT",
                characters="Hi",
                fontSize=16,
                textAutoResize="NONE",
                box={"x": 0, "y": 0, "width": 400, "height": 80},
                boundingBox={"x": 0, "y": 0, "width": 40, "height": 18},
            ),
        ],
    )
    auditor = auditor_module.PreciseModeAuditor(root)
    result = auditor.audit()
    snug = next(c for c in result["checks"] if c["check_id"] == "snug_text")
    assert not snug["passed"]
    assert snug["details"][0]["reason"] == "bounding-box-exceeds-content-box"
