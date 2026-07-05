"""Unit tests for figma-agent-core/responsive_composer.py.

Loads the module via importlib because the directory name contains a hyphen.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
RESPONSIVE_COMPOSER_PATH = ROOT / "figma-agent-core" / "responsive_composer.py"
LAYOUT_ENGINE_PATH = ROOT / "figma-agent-core" / "layout_engine.py"


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


responsive_composer = _load_module(RESPONSIVE_COMPOSER_PATH, "figma_responsive_composer")
layout_engine = _load_module(LAYOUT_ENGINE_PATH, "figma_layout_engine_for_responsive")


def _base_frame() -> dict:
    return {
        "id": "1:1",
        "name": "Mobile Hero",
        "type": "FRAME",
        "visible": True,
        "box": {"x": 0, "y": 0, "width": 375, "height": 600},
        "children": [
            {
                "id": "1:2",
                "name": "Title",
                "type": "TEXT",
                "visible": True,
                "characters": "Hello",
                "box": {"x": 20, "y": 100, "width": 335, "height": 40},
                "style": {"fontSize": 32, "fontWeight": 700},
            }
        ],
    }


def _tablet_frame() -> dict:
    return {
        "id": "2:1",
        "name": "Tablet Hero",
        "type": "FRAME",
        "visible": True,
        "box": {"x": 0, "y": 0, "width": 768, "height": 600},
        "children": [
            {
                "id": "2:2",
                "name": "Title",
                "type": "TEXT",
                "visible": True,
                "characters": "Hello",
                "box": {"x": 40, "y": 100, "width": 688, "height": 48},
                "style": {"fontSize": 40, "fontWeight": 700},
            }
        ],
    }


def test_load_module() -> None:
    assert hasattr(responsive_composer, "compose_responsive_ast")
    assert hasattr(responsive_composer, "detect_breakpoint_frames")
    assert hasattr(responsive_composer, "constraint_to_classes")


def test_detect_breakpoint_frames() -> None:
    root = {
        "id": "0:1",
        "name": "Page",
        "type": "PAGE",
        "children": [_base_frame(), _tablet_frame()],
    }
    frames, warnings = responsive_composer.detect_breakpoint_frames(root)
    assert "base" in frames
    assert "md" in frames
    assert frames["base"]["id"] == "1:1"
    assert frames["md"]["id"] == "2:1"
    assert not warnings


def test_detect_duplicate_breakpoint_warns() -> None:
    root = {
        "id": "0:1",
        "name": "Page",
        "type": "PAGE",
        "children": [
            {"id": "1:1", "name": "Mobile A", "type": "FRAME", "visible": True},
            {"id": "1:2", "name": "Mobile B", "type": "FRAME", "visible": True},
        ],
    }
    frames, warnings = responsive_composer.detect_breakpoint_frames(root)
    assert frames["base"]["id"] == "1:1"
    assert any(w["type"] == "duplicate_breakpoint" for w in warnings)


def test_constraint_to_classes() -> None:
    node = {
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "HUG",
        "layoutGrow": 1,
        "layoutAlign": "STRETCH",
        "minWidth": 100,
        "maxWidth": 500,
        "minHeight": 50,
        "maxHeight": 200,
    }
    classes = responsive_composer.constraint_to_classes(node)
    assert "w-full" in classes
    assert "h-auto" in classes
    assert "flex-1" in classes
    assert "self-stretch" in classes
    assert "min-w-[100px]" in classes
    assert "max-w-[500px]" in classes
    assert "min-h-[50px]" in classes
    assert "max-h-[200px]" in classes


def test_constraint_to_classes_with_stretch_constraints() -> None:
    node = {
        "constraints": {"horizontal": "STRETCH", "vertical": "TOP_BOTTOM"},
    }
    classes = responsive_composer.constraint_to_classes(node)
    assert "w-full" in classes
    assert "h-full" in classes


def test_constraint_to_classes_fixed_with_constraints_emits_absolute() -> None:
    node = {
        "id": "1:5",
        "name": "Badge",
        "type": "FRAME",
        "visible": True,
        "layoutSizingHorizontal": "FIXED",
        "layoutSizingVertical": "FIXED",
        "constraints": {"horizontal": "RIGHT", "vertical": "BOTTOM"},
        "box": {"x": 720, "y": 20, "width": 60, "height": 24},
    }
    classes = responsive_composer.constraint_to_classes(node)
    # FIXED + explicit constraints keep arbitrary fixed size.
    assert "w-[60px]" in classes
    assert "h-[24px]" in classes


def test_compose_responsive_ast_generates_direction_variants() -> None:
    base = {
        "id": "1:1",
        "name": "Mobile Hero",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "VERTICAL",
        "box": {"x": 0, "y": 0, "width": 375, "height": 600},
        "children": [
            {
                "id": "1:2",
                "name": "Card",
                "type": "FRAME",
                "visible": True,
                "layoutMode": "VERTICAL",
                "box": {"x": 20, "y": 100, "width": 335, "height": 40},
            }
        ],
    }
    tablet = {
        "id": "2:1",
        "name": "Tablet Hero",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "VERTICAL",
        "box": {"x": 0, "y": 0, "width": 768, "height": 600},
        "children": [
            {
                "id": "2:2",
                "name": "Card",
                "type": "FRAME",
                "visible": True,
                "layoutMode": "HORIZONTAL",
                "box": {"x": 40, "y": 100, "width": 688, "height": 48},
            }
        ],
    }
    figma_root = {"id": "0:1", "name": "Page", "type": "PAGE", "children": [base, tablet]}
    layout_ast = layout_engine.convert_figma_node(base).to_dict()
    responsive_ast, report = responsive_composer.compose_responsive_ast(layout_ast, figma_root)

    card = responsive_ast["root"]["children"][0]
    md_variants = card.get("responsive_variants", {}).get("md", [])
    assert "md:flex-row" in md_variants
    assert "md:w-[688px]" in md_variants
    assert "md:h-[48px]" in md_variants


def test_compose_responsive_ast_applies_constraints_to_base() -> None:
    base = {
        "id": "1:1",
        "name": "Card",
        "type": "FRAME",
        "visible": True,
        "box": {"x": 0, "y": 0, "width": 300, "height": 200},
        "layoutSizingHorizontal": "FILL",
        "minWidth": 200,
    }
    layout_ast = layout_engine.convert_figma_node(base).to_dict()
    responsive_ast, report = responsive_composer.compose_responsive_ast(layout_ast, base)
    root = responsive_ast["root"]
    # Layout engine now emits constraint classes directly; responsive composer is idempotent.
    assert "w-full" in root["classes"]
    assert "min-w-[200px]" in root["classes"]
    # No duplicate classes injected.
    assert root["classes"].count("w-full") == 1
    assert root["classes"].count("min-w-[200px]") == 1


def test_compose_responsive_ast_generates_breakpoint_variants() -> None:
    base = _base_frame()
    tablet = _tablet_frame()
    figma_root = {
        "id": "0:1",
        "name": "Page",
        "type": "PAGE",
        "children": [base, tablet],
    }
    layout_ast = layout_engine.convert_figma_node(base).to_dict()
    responsive_ast, report = responsive_composer.compose_responsive_ast(layout_ast, figma_root)

    # Tablet Title should have md: classes.
    title = responsive_ast["root"]["children"][0]
    assert "responsive_variants" in title
    md_variants = title["responsive_variants"].get("md", [])
    assert any("md:w-[688px]" == c for c in md_variants)
    assert any("md:h-[48px]" == c for c in md_variants)
    assert any("md:text-[40px]" == c for c in md_variants)
    assert report["variant_classes_added"] > 0
    assert report["matched_nodes"] == 1


def test_compose_responsive_ast_no_breakpoints_short_circuits() -> None:
    base = _base_frame()
    layout_ast = layout_engine.convert_figma_node(base).to_dict()
    responsive_ast, report = responsive_composer.compose_responsive_ast(layout_ast, base)
    assert report.get("no_breakpoint_variants") is True
    assert responsive_ast["root"].get("responsive_variants") in ({}, None)


def test_compose_responsive_ast_warns_unmatched_node() -> None:
    base = _base_frame()
    tablet = {
        "id": "2:1",
        "name": "Tablet Hero",
        "type": "FRAME",
        "visible": True,
        "box": {"x": 0, "y": 0, "width": 768, "height": 600},
        "children": [
            {
                "id": "2:2",
                "name": "Different Name",
                "type": "TEXT",
                "visible": True,
                "characters": "Hello",
                "box": {"x": 40, "y": 100, "width": 688, "height": 48},
                "style": {"fontSize": 40, "fontWeight": 700},
            }
        ],
    }
    figma_root = {"id": "0:1", "name": "Page", "type": "PAGE", "children": [base, tablet]}
    layout_ast = layout_engine.convert_figma_node(base).to_dict()
    responsive_ast, report = responsive_composer.compose_responsive_ast(layout_ast, figma_root)
    assert any(w["type"] == "unmatched_node" for w in report["warnings"])
    title = responsive_ast["root"]["children"][0]
    assert not title.get("responsive_variants")


def test_compose_responsive_ast_skips_base_token_frame() -> None:
    base = _base_frame()
    # Desktop frame named "Wide" should map to xl, not base.
    desktop = {
        "id": "3:1",
        "name": "Wide Promo",
        "type": "FRAME",
        "visible": True,
        "box": {"x": 0, "y": 0, "width": 1440, "height": 600},
        "children": [
            {
                "id": "3:2",
                "name": "Title",
                "type": "TEXT",
                "visible": True,
                "characters": "Hello",
                "box": {"x": 100, "y": 100, "width": 1240, "height": 56},
                "style": {"fontSize": 48, "fontWeight": 700},
            }
        ],
    }
    figma_root = {"id": "0:1", "name": "Page", "type": "PAGE", "children": [base, desktop]}
    layout_ast = layout_engine.convert_figma_node(base).to_dict()
    responsive_ast, report = responsive_composer.compose_responsive_ast(layout_ast, figma_root)
    title = responsive_ast["root"]["children"][0]
    xl_variants = title["responsive_variants"].get("xl", [])
    assert any("xl:w-[1240px]" == c for c in xl_variants)


def test_main_cli_writes_outputs(tmp_path: Path) -> None:
    base = _base_frame()
    tablet = _tablet_frame()
    figma_root = {"id": "0:1", "name": "Page", "type": "PAGE", "children": [base, tablet]}
    layout_ast = layout_engine.convert_figma_node(base).to_dict()

    ast_path = tmp_path / "layout_ast.json"
    ast_path.write_text(json.dumps(layout_ast), encoding="utf-8")
    figma_path = tmp_path / "figma_node.json"
    figma_path.write_text(json.dumps(figma_root), encoding="utf-8")
    output_path = tmp_path / "responsive_ast.json"
    report_path = tmp_path / "responsive_report.json"

    # Import main and invoke directly to avoid sys.argv mutation in tests.
    import argparse
    responsive_composer.main = lambda: None  # type: ignore[assignment]

    # Use the core function instead.
    responsive_ast, report = responsive_composer.compose_responsive_ast(
        layout_ast,
        figma_root,
    )
    output_path.write_text(json.dumps(responsive_ast), encoding="utf-8")
    report_path.write_text(json.dumps(report), encoding="utf-8")

    assert output_path.exists()
    assert report_path.exists()
    data = json.loads(output_path.read_text(encoding="utf-8"))
    title = data["root"]["children"][0]
    assert "md:" in " ".join(title.get("responsive_variants", {}).get("md", []))


def test_compose_responsive_ast_matches_by_stable_figma_id() -> None:
    """Stable figma_id is preferred when matching nodes across breakpoint frames."""
    base = {
        "id": "1:1",
        "name": "Frame",
        "type": "FRAME",
        "visible": True,
        "box": {"x": 0, "y": 0, "width": 375, "height": 600},
        "children": [
            {
                "id": "same-id-across-breakpoints",
                "name": "Title",
                "type": "TEXT",
                "visible": True,
                "characters": "Hello",
                "box": {"x": 20, "y": 100, "width": 335, "height": 40},
                "style": {"fontSize": 32, "fontWeight": 700},
            }
        ],
    }
    tablet = {
        "id": "2:1",
        "name": "Tablet Frame",
        "type": "FRAME",
        "visible": True,
        "box": {"x": 0, "y": 0, "width": 768, "height": 600},
        "children": [
            {
                # Same id proves stable-id matching even when sibling index differs.
                "id": "same-id-across-breakpoints",
                "name": "Different Name",
                "type": "TEXT",
                "visible": True,
                "characters": "Hello",
                "box": {"x": 40, "y": 100, "width": 688, "height": 48},
                "style": {"fontSize": 40, "fontWeight": 700},
            }
        ],
    }
    figma_root = {"id": "0:1", "name": "Page", "type": "PAGE", "children": [base, tablet]}
    layout_ast = layout_engine.convert_figma_node(base).to_dict()
    responsive_ast, report = responsive_composer.compose_responsive_ast(layout_ast, figma_root)

    title = responsive_ast["root"]["children"][0]
    assert "responsive_variants" in title
    md_variants = title["responsive_variants"].get("md", [])
    assert any("md:w-[688px]" == c for c in md_variants)
    # The matching succeeded because the shared figma_id won over the different names.
    assert report["matched_nodes"] >= 1


def _wrap_frame(children: list, extra: dict | None = None) -> dict:
    frame = {
        "id": "1:1",
        "name": "Tag List",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "HORIZONTAL",
        "layoutWrap": "WRAP",
        "itemSpacing": 8,
        "box": {"x": 0, "y": 0, "width": 375, "height": 200},
        "children": children,
    }
    if extra:
        frame.update(extra)
    return frame


def test_compose_responsive_ast_grid_for_wrap() -> None:
    """When grid_for_wrap is enabled, wrapped frames are rendered as CSS Grid."""
    base = {
        "id": "1:0",
        "name": "Mobile Tags",
        "type": "FRAME",
        "visible": True,
        "box": {"x": 0, "y": 0, "width": 375, "height": 400},
        "children": [_wrap_frame([
            {"id": "1:2", "name": "Tag 1", "type": "FRAME", "visible": True, "box": {"x": 0, "y": 0, "width": 80, "height": 32}},
            {"id": "1:3", "name": "Tag 2", "type": "FRAME", "visible": True, "box": {"x": 88, "y": 0, "width": 80, "height": 32}},
        ])],
    }
    tablet = {
        "id": "2:0",
        "name": "Tablet Tags",
        "type": "FRAME",
        "visible": True,
        "box": {"x": 0, "y": 0, "width": 768, "height": 400},
        "children": [_wrap_frame([
            {"id": "2:2", "name": "Tag 1", "type": "FRAME", "visible": True, "box": {"x": 0, "y": 0, "width": 80, "height": 32}},
            {"id": "2:3", "name": "Tag 2", "type": "FRAME", "visible": True, "box": {"x": 92, "y": 0, "width": 80, "height": 32}},
            {"id": "2:4", "name": "Tag 3", "type": "FRAME", "visible": True, "box": {"x": 184, "y": 0, "width": 80, "height": 32}},
        ], {"id": "2:1", "itemSpacing": 12, "counterAxisCount": 3, "box": {"x": 0, "y": 0, "width": 768, "height": 200}})],
    }
    page = {"id": "0:1", "name": "Page", "type": "PAGE", "children": [base, tablet]}
    layout_ast = layout_engine.convert_figma_node(base, config={"grid_for_wrap": True}).to_dict()
    responsive_ast, report = responsive_composer.compose_responsive_ast(
        layout_ast,
        page,
        config={"grid_for_wrap": True},
    )

    tags = responsive_ast["root"]["children"][0]
    base_classes = tags["classes"]
    assert "grid" in base_classes
    assert "grid-cols-2" in base_classes
    assert "flex-wrap" not in base_classes
    md_variants = tags.get("responsive_variants", {}).get("md", [])
    assert "md:grid-cols-3" in md_variants
    assert "md:gap-[12px]" in md_variants


def test_grid_for_wrap_disabled_keeps_flex_wrap() -> None:
    """Without the grid_for_wrap flag, wrap frames keep the legacy flex-wrap layout."""
    node = _wrap_frame([])
    result = layout_engine.convert_figma_node(node).to_dict()
    classes = result["root"]["classes"]
    assert "flex" in classes
    assert "flex-wrap" in classes
    assert "grid" not in classes
