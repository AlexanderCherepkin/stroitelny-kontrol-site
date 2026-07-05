"""Unit tests for figma-agent-core/content_model_extractor.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
EXTRACTOR_PATH = ROOT / "figma-agent-core" / "content_model_extractor.py"


def _load_extractor_module() -> Any:
    spec = importlib.util.spec_from_file_location("figma_content_model_extractor", str(EXTRACTOR_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_content_model_extractor"] = module
    # content_model_extractor imports content_model from the same directory
    sys.path.insert(0, str(EXTRACTOR_PATH.parent))
    spec.loader.exec_module(module)
    return module


extractor_module = _load_extractor_module()


def test_module_loads() -> None:
    assert hasattr(extractor_module, "extract_content_model")
    assert hasattr(extractor_module, "main")


def test_extract_content_model_returns_page_sections_and_data(tmp_path: Path) -> None:
    ast = {
        "root": {
            "tag": "div",
            "children": [
                {
                    "tag": "section",
                    "figma_name": "Hero",
                    "classes": ["w-full", "bg-primary"],
                    "children": [
                        {"tag": "h1", "text": "Build fast", "classes": ["text-foreground"]},
                    ],
                },
                {
                    "tag": "section",
                    "figma_name": "Features",
                    "classes": ["w-full"],
                    "children": [
                        {"tag": "h2", "text": "Features", "classes": []},
                    ],
                },
            ],
        }
    }
    result = extractor_module.extract_content_model(
        ast,
        output_dir=str(tmp_path / "sections"),
        page_output=str(tmp_path / "page.tsx"),
        data_output=str(tmp_path / "page.data.ts"),
        content_model_output=str(tmp_path / "content_model.json"),
        root_dir=str(tmp_path),
    )
    assert hasattr(result, "page_code")
    assert hasattr(result, "data_code")
    assert hasattr(result, "sections")
    assert len(result.sections) == 2
    names = {s.name for s in result.sections}
    assert names == {"Hero", "Features"}

    # Files are written
    assert (tmp_path / "sections" / "Hero.tsx").exists()
    assert (tmp_path / "sections" / "Features.tsx").exists()
    assert (tmp_path / "page.tsx").exists()
    assert (tmp_path / "page.data.ts").exists()
    assert (tmp_path / "content_model.json").exists()

    # Content model JSON has expected shape
    cm = json.loads((tmp_path / "content_model.json").read_text(encoding="utf-8"))
    assert cm["version"] == "1"
    assert len(cm["sections"]) == 2


def test_extract_content_model_rejects_outside_workspace(tmp_path: Path) -> None:
    ast = {"root": {"tag": "div", "children": []}}
    outside = tmp_path.parent / "outside"
    with pytest.raises(ValueError, match="outside workspace"):
        extractor_module.extract_content_model(ast, output_dir=str(outside), root_dir=str(tmp_path))


def test_extract_content_model_propagates_component_mapper(tmp_path: Path) -> None:
    ast = {
        "root": {
            "tag": "div",
            "children": [
                {
                    "tag": "section",
                    "figma_name": "Hero",
                    "classes": ["w-full"],
                    "children": [
                        {
                            "tag": "button",
                            "component_ref": "Button",
                            "component_set_id": "10:1",
                            "is_instance": True,
                            "variant_properties": {"Variant": "Primary"},
                            "classes": ["bg-primary"],
                        },
                    ],
                }
            ],
        }
    }
    mapper = {
        "version": "1.0",
        "mappings": {
            "10:1": {
                "pascal_name": "Button",
                "react_component": {"export_name": "Button", "import_path": "@/components/ui/Button"},
                "variant_prop_map": {"Variant": "variant"},
                "value_mapping": {"variant": {"Primary": "primary"}},
                "default_props": {"variant": "primary"},
            }
        },
    }
    result = extractor_module.extract_content_model(
        ast,
        output_dir=str(tmp_path / "sections"),
        page_output=str(tmp_path / "page.tsx"),
        data_output=str(tmp_path / "page.data.ts"),
        content_model_output=str(tmp_path / "content_model.json"),
        root_dir=str(tmp_path),
        component_mapper=mapper,
    )
    assert len(result.sections) == 1
    assert "Button" in result.sections[0].component_code
