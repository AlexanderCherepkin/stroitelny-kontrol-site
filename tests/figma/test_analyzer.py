"""Unit tests for figma-agent-core/analyzer.py semantic naming and metadata extraction."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
ANALYZER_PATH = ROOT / "figma-agent-core" / "analyzer.py"


def _load_analyzer() -> Any:
    spec = importlib.util.spec_from_file_location("figma_analyzer", str(ANALYZER_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_analyzer"] = module
    spec.loader.exec_module(module)
    return module


analyzer = _load_analyzer()


def test_clean_name_removes_emoji_and_suffixes() -> None:
    assert analyzer._clean_name("🚀 Hero Section / 1") == "Hero Section"
    assert analyzer._clean_name("Frame 123") == "Frame"
    assert analyzer._clean_name("✨ Pricing!!! Card") == "Pricing Card"
    assert analyzer._clean_name("Group / 2") == "Group"


def test_is_generic_name_detects_generic() -> None:
    assert analyzer._is_generic_name("Frame 1")
    assert analyzer._is_generic_name("Group / 2")
    assert analyzer._is_generic_name("Rectangle 10")
    assert analyzer._is_generic_name("Container")
    assert not analyzer._is_generic_name("HeroSection")
    assert not analyzer._is_generic_name("PricingCard")


def test_infer_semantic_name_prefers_description_when_name_is_generic() -> None:
    node = {
        "name": "Frame 1",
        "type": "FRAME",
        "description": "Hero section with headline and CTA",
    }
    assert analyzer.infer_semantic_name(node) == "HeroSectionWithHeadlineAndCTA"


def test_infer_semantic_name_prefers_annotations_when_name_and_description_are_generic() -> None:
    node = {
        "name": "Container",
        "type": "FRAME",
        "description": "",
        "annotations": [
            {"label": "Pricing", "description": "Monthly plan card"},
        ],
    }
    assert analyzer.infer_semantic_name(node) == "PricingMonthlyPlanCard"


def test_infer_semantic_name_keeps_meaningful_name() -> None:
    node = {"name": "🚀 Features", "type": "FRAME"}
    assert analyzer.infer_semantic_name(node) == "Features"


def test_infer_semantic_name_fallback_by_type() -> None:
    node = {"name": "Frame 1", "type": "FRAME"}
    assert analyzer.infer_semantic_name(node, fallback="Section") == "Section"

    node = {"name": "Vector 1", "type": "VECTOR"}
    assert analyzer.infer_semantic_name(node) == "Vector"


def test_get_node_details_includes_description_and_annotations(tmp_path: Path) -> None:
    root = {
        "id": "page",
        "name": "Page",
        "type": "FRAME",
        "children": [
            {
                "id": "1:1",
                "name": "Frame 1",
                "type": "FRAME",
                "description": "Hero area",
                "annotations": [{"label": "Main CTA", "description": "Primary conversion"}],
                "children": [],
            }
        ],
    }
    figma_file = tmp_path / "figma_node.json"
    figma_file.write_text(json.dumps(root, ensure_ascii=False), encoding="utf-8")
    details = analyzer.get_node_details("1:1", filepath=str(figma_file))
    assert details is not None
    assert details["description"] == "Hero area"
    assert details["annotations"] == [{"label": "Main CTA", "description": "Primary conversion"}]
    assert details["semantic_name"] == "HeroArea"


def test_list_top_level_nodes_includes_semantic_name() -> None:
    root = {
        "id": "page",
        "name": "Page",
        "type": "FRAME",
        "children": [
            {
                "id": "1:1",
                "name": "Frame 1",
                "type": "FRAME",
                "description": "Hero section",
            },
            {
                "id": "1:2",
                "name": "Pricing",
                "type": "FRAME",
            },
        ],
    }
    nodes = analyzer.list_top_level_nodes(root)
    assert nodes[0]["semantic_name"] == "HeroSection"
    assert nodes[1]["semantic_name"] == "Pricing"
