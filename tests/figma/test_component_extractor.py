"""Unit tests for figma-agent-core/component_extractor.py.

Loads the module via importlib because the directory name contains a hyphen.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
EXTRACTOR_PATH = ROOT / "figma-agent-core" / "component_extractor.py"


def _load_component_extractor() -> Any:
    spec = importlib.util.spec_from_file_location("figma_component_extractor", str(EXTRACTOR_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_component_extractor"] = module
    spec.loader.exec_module(module)
    return module


extractor = _load_component_extractor()


def _minimal_ast(root_children: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"root": {"tag": "section", "figma_id": "0:1", "figma_name": "Canvas", "children": root_children}}


def test_load_module() -> None:
    assert hasattr(extractor, "ComponentExtractor")
    assert hasattr(extractor, "run_extraction")


def test_named_pattern_extraction(tmp_path: Path) -> None:
    ast = _minimal_ast([
        {
            "tag": "header",
            "figma_id": "1:1",
            "figma_name": "Hero section",
            "classes": ["flex", "flex-col", "items-center"],
            "children": [
                {"tag": "h1", "figma_id": "1:2", "text": "Hero Title", "classes": ["text-[40px]"]},
            ],
        }
    ])

    ext = extractor.ComponentExtractor(output_dir=str(tmp_path / "components"), root_dir=str(tmp_path))
    page_ast, components = ext.extract(ast)

    assert len(components) == 1
    assert components[0].name == "HeroSection"
    assert (tmp_path / "components" / "HeroSection.tsx").exists()
    assert page_ast["root"]["children"][0].get("component") is True


def test_structural_duplicate_extraction(tmp_path: Path) -> None:
    card = {
        "tag": "article",
        "figma_id": "2:1",
        "figma_name": "Card",
        "classes": ["flex", "flex-col", "bg-white", "rounded-xl"],
        "children": [
            {"tag": "h3", "figma_id": "2:2", "figma_name": "Title", "text": "Title", "classes": ["text-[20px]"]},
            {"tag": "p", "figma_id": "2:3", "figma_name": "Desc", "text": "Desc", "classes": ["text-[14px]"]},
        ],
    }
    ast = _minimal_ast([
        {**card, "figma_id": "3:1", "figma_name": "Item 1"},
        {**card, "figma_id": "3:2", "figma_name": "Item 2"},
    ])

    ext = extractor.ComponentExtractor(output_dir=str(tmp_path / "components"), root_dir=str(tmp_path))
    page_ast, components = ext.extract(ast)

    assert len(components) == 2
    names = [c.name for c in components]
    assert "FeatureCard" in names
    assert "FeatureCard2" in names
    assert len(page_ast["root"]["children"]) == 2
    assert page_ast["root"]["children"][0].get("component") is True


def test_path_traversal_blocked(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        extractor.ComponentExtractor(output_dir="../outside", root_dir=str(tmp_path))


def test_no_candidates_passthrough(tmp_path: Path) -> None:
    ast = _minimal_ast([
        {"tag": "h1", "figma_id": "4:1", "text": "Only heading", "classes": ["text-[40px]"]},
    ])

    ext = extractor.ComponentExtractor(output_dir=str(tmp_path / "components"), root_dir=str(tmp_path))
    page_ast, components = ext.extract(ast)

    assert len(components) == 0
    assert page_ast["root"]["children"][0].get("text") == "Only heading"


def test_figma_component_type_extraction(tmp_path: Path) -> None:
    ast = _minimal_ast([
        {
            "tag": "button",
            "figma_id": "5:1",
            "figma_name": "Primary Button",
            "figma_type": "COMPONENT",
            "classes": ["bg-blue-500", "text-white"],
            "children": [
                {"tag": "span", "figma_id": "5:2", "text": "Click", "classes": ["text-[14px]"]},
            ],
        }
    ])

    ext = extractor.ComponentExtractor(output_dir=str(tmp_path / "components"), root_dir=str(tmp_path))
    page_ast, components = ext.extract(ast)

    assert len(components) == 1
    assert components[0].name == "PrimaryButton"
    assert page_ast["root"]["children"][0].get("component") is True


def test_nested_deduplication(tmp_path: Path) -> None:
    ast = _minimal_ast([
        {
            "tag": "article",
            "figma_id": "6:1",
            "figma_name": "Card",
            "classes": ["bg-white"],
            "children": [
                {"tag": "button", "figma_id": "6:2", "figma_name": "CTA", "classes": ["bg-blue-500"],
                 "children": [{"tag": "span", "figma_id": "6:3", "text": "Go", "classes": []}]},
            ],
        }
    ])

    ext = extractor.ComponentExtractor(output_dir=str(tmp_path / "components"), root_dir=str(tmp_path))
    page_ast, components = ext.extract(ast)

    names = [c.name for c in components]
    assert "Card" in names
    # Ensure not both extracted when one is nested inside the other.
    assert len(components) == 1


def test_run_extraction_creates_outputs(tmp_path: Path) -> None:
    ast = _minimal_ast([
        {
            "tag": "header",
            "figma_id": "7:1",
            "figma_name": "Hero",
            "classes": ["flex"],
            "children": [
                {"tag": "h1", "figma_id": "7:2", "text": "Hello", "classes": ["font-[Inter]"]},
            ],
        }
    ])

    ast_path = tmp_path / "layout_ast.json"
    ast_path.write_text(json.dumps(ast), encoding="utf-8")

    result = extractor.run_extraction(
        ast_path=str(ast_path),
        output_dir=str(tmp_path / "components"),
        page_ast_output=str(tmp_path / "page_ast.json"),
        component_map_output=str(tmp_path / "component_map.json"),
        root_dir=str(tmp_path),
    )

    assert result["extracted_count"] == 1
    assert (tmp_path / "components" / "Hero.tsx").exists()
    assert (tmp_path / "page_ast.json").exists()
    assert (tmp_path / "component_map.json").exists()

    component_code = (tmp_path / "components" / "Hero.tsx").read_text(encoding="utf-8")
    assert "export default function Hero()" in component_code
    assert 'import { Inter } from "next/font/google"' in component_code

    component_map = json.loads((tmp_path / "component_map.json").read_text(encoding="utf-8"))
    assert component_map["components"][0]["name"] == "Hero"
    assert component_map["components"][0]["import_path"] == "@/app/components/Hero"


def test_min_duplicates_threshold(tmp_path: Path) -> None:
    item = {
        "tag": "article",
        "figma_id": "8:1",
        "figma_name": "Item",
        "classes": ["flex", "bg-white"],
        "children": [
            {"tag": "h3", "figma_id": "8:2", "text": "T", "classes": ["text-[20px]"]},
        ],
    }
    ast = _minimal_ast([
        {**item, "figma_id": "9:1"},
        {**item, "figma_id": "9:2"},
    ])

    ext = extractor.ComponentExtractor(
        output_dir=str(tmp_path / "components"),
        root_dir=str(tmp_path),
        min_duplicates=3,
    )
    page_ast, components = ext.extract(ast)

    assert len(components) == 0


def test_component_name_sanitization(tmp_path: Path) -> None:
    ast = _minimal_ast([
        {
            "tag": "div",
            "figma_id": "10:1",
            "figma_name": "123 bad-name card!",
            "classes": ["flex"],
            "children": [
                {"tag": "p", "figma_id": "10:2", "text": "Text", "classes": []},
                {"tag": "span", "figma_id": "10:3", "text": "More", "classes": []},
            ],
        }
    ])

    ext = extractor.ComponentExtractor(output_dir=str(tmp_path / "components"), root_dir=str(tmp_path))
    page_ast, components = ext.extract(ast)

    assert len(components) == 1
    assert components[0].name == "Figma123BadNameCard"
