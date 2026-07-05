"""Unit tests for figma-agent-core/spec_writer.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SPEC_WRITER_PATH = ROOT / "figma-agent-core" / "spec_writer.py"


def _load_spec_writer() -> Any:
    core_dir = str(ROOT / "figma-agent-core")
    if core_dir not in sys.path:
        sys.path.insert(0, core_dir)
    spec = importlib.util.spec_from_file_location("figma_spec_writer", str(SPEC_WRITER_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_spec_writer"] = module
    spec.loader.exec_module(module)
    return module


spec_writer = _load_spec_writer()


def test_to_pascal_case_normalizes_name() -> None:
    assert spec_writer._to_pascal_case("Hero Section") == "HeroSection"
    assert spec_writer._to_pascal_case("123-section") == "Figma123Section"


def test_collect_fills_extracts_unique_hex_colors() -> None:
    nodes = [
        {
            "name": "Card",
            "fills": [
                {"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}},
                {"type": "SOLID", "color": {"r": 1, "g": 0, "b": 0, "a": 1}},
            ],
        },
        {
            "name": "Button",
            "fills": [
                {"hex": "#ff0000", "rgb": "rgb(255, 0, 0)"},
            ],
        },
    ]
    fills = spec_writer._collect_fills(nodes)
    hexes = {f["hex"].lower() for f in fills}
    assert "#ffffff" in hexes
    assert "#ff0000" in hexes


def test_collect_typography_skips_missing_font_size() -> None:
    nodes = [
        {"type": "TEXT", "style": {"fontFamily": "Inter", "fontSize": 16, "fontWeight": 400}, "characters": "A"},
        {"type": "TEXT", "style": {"fontFamily": "Inter"}, "characters": "B"},
    ]
    typography = spec_writer._collect_typography(nodes)
    assert len(typography) == 1
    assert typography[0]["fontSize"] == 16


def test_generate_spec_writes_markdown(tmp_path: Path) -> None:
    node = {
        "id": "1:1",
        "name": "Landing Page",
        "type": "FRAME",
        "children": [
            {
                "id": "2:1",
                "name": "Hero",
                "type": "FRAME",
                "layoutMode": "VERTICAL",
                "itemSpacing": 16,
                "paddingTop": 24,
                "paddingRight": 24,
                "paddingBottom": 24,
                "paddingLeft": 24,
                "children": [
                    {"id": "3:1", "name": "Title", "type": "TEXT", "characters": "Hello", "style": {"fontFamily": "Inter", "fontSize": 32, "fontWeight": 700}},
                ],
            }
        ],
    }
    output = tmp_path / "spec.md"
    path = spec_writer.generate_spec(node, output_path=str(output))
    assert path == str(output)
    text = output.read_text(encoding="utf-8")
    assert "# Техническое задание: Landing Page" in text
    assert "LandingPage" in text
    assert "AutoLayout vertical" in text
    assert "Hello" in text


def test_extract_layout_rules_includes_autolayout() -> None:
    node = {
        "name": "Card",
        "type": "FRAME",
        "layoutMode": "VERTICAL",
        "itemSpacing": 8,
        "paddingTop": 4,
        "paddingRight": 4,
        "paddingBottom": 4,
        "paddingLeft": 4,
        "children": [],
    }
    rules = spec_writer._extract_layout_rules(node)
    assert any("AutoLayout vertical" in rule for rule in rules)
