"""Unit tests for figma-agent-core/content_model.py.

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
CONTENT_MODEL_PATH = ROOT / "figma-agent-core" / "content_model.py"


def _load_content_model() -> Any:
    spec = importlib.util.spec_from_file_location("figma_content_model", str(CONTENT_MODEL_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_content_model"] = module
    spec.loader.exec_module(module)
    return module


content_model = _load_content_model()


def test_module_loads() -> None:
    assert hasattr(content_model, "build_content_model")
    assert hasattr(content_model, "ContentModelResult")


def test_splits_ast_into_page_sections_and_data(tmp_path: Path) -> None:
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
                        {"tag": "img", "src": "/images/hero.png", "alt": "Hero", "classes": ["w-full"]},
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

    result = content_model.build_content_model(
        ast,
        output_dir=str(tmp_path / "sections"),
        page_output=str(tmp_path / "page.tsx"),
        data_output=str(tmp_path / "page.data.ts"),
        content_model_output=str(tmp_path / "content_model.json"),
        root_dir=str(tmp_path),
    )

    assert len(result.sections) == 2
    assert "Hero" in result.data
    assert "Features" in result.data
    assert result.data["Hero"]["heading"] == "Build fast"
    assert result.data["Hero"]["image"] == "/images/hero.png"
    assert result.data["Features"]["heading"] == "Features"

    assert 'import { pageData, sections } from "./page.data"' in result.page_code
    assert "sections.map" in result.page_code
    assert 'case "Hero":' in result.page_code
    assert "export const pageData" in result.data_code
    assert "export const sections" in result.data_code

    cm_file = tmp_path / "content_model.json"
    assert cm_file.exists()
    cm = json.loads(cm_file.read_text(encoding="utf-8"))
    assert cm["version"] == "1"
    assert any(s["name"] == "Hero" for s in cm["sections"])
    hero_section = next(s for s in cm["sections"] if s["name"] == "Hero")
    assert any(f["name"] == "heading" for f in hero_section["fields"])
    assert any(f["name"] == "image" for f in hero_section["fields"])
    heading_field = next(f for f in hero_section["fields"] if f["name"] == "heading")
    assert heading_field["type"] == "text"
    assert heading_field["label"] == "Title"
    assert heading_field["required"] is True
    assert heading_field["role"] == "heading"
    image_field = next(f for f in hero_section["fields"] if f["name"] == "image")
    assert image_field["type"] == "image"
    assert image_field["label"] == "Image"
    assert image_field["required"] is False

    hero_file = tmp_path / "sections" / "Hero.tsx"
    features_file = tmp_path / "sections" / "Features.tsx"
    assert hero_file.exists()
    assert features_file.exists()

    hero_code = hero_file.read_text(encoding="utf-8")
    assert "export interface HeroProps" in hero_code
    assert "heading?: string" in hero_code
    assert "image?: string" in hero_code
    assert "{props.heading}" in hero_code
    assert "{props.image}" in hero_code


def test_rejects_path_traversal(tmp_path: Path) -> None:
    ast = {"root": {"tag": "div", "children": []}}
    with pytest.raises(ValueError):
        content_model.build_content_model(
            ast,
            output_dir=str(tmp_path.parent / "outside" / "sections"),
            root_dir=str(tmp_path),
        )


def test_skips_component_context_nodes(tmp_path: Path) -> None:
    ast = {
        "root": {
            "tag": "div",
            "children": [
                {
                    "tag": "section",
                    "figma_name": "Hero",
                    "classes": [],
                    "children": [{"tag": "h1", "text": "Hi", "classes": []}],
                },
                {
                    "tag": "div",
                    "component_context": True,
                    "is_instance": False,
                    "children": [],
                },
            ],
        }
    }
    result = content_model.build_content_model(
        ast,
        output_dir=str(tmp_path / "sections"),
        page_output=str(tmp_path / "page.tsx"),
        data_output=str(tmp_path / "page.data.ts"),
        content_model_output=str(tmp_path / "content_model.json"),
        root_dir=str(tmp_path),
    )
    assert len(result.sections) == 1
    assert result.sections[0].name == "Hero"


def test_uses_mapper_import_path_for_component_refs(tmp_path: Path) -> None:
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
                            "figma_id": "30:2",
                            "figma_name": "Card Button",
                            "figma_type": "INSTANCE",
                            "component_ref": "Button",
                            "component_set_id": "10:1",
                            "is_instance": True,
                            "variant_props": {"Variant": "Primary", "Size": "Large"},
                            "classes": [],
                        }
                    ],
                }
            ],
        }
    }
    mapper = {
        "mappings": {
            "10:1": {
                "react_component": {
                    "import_path": "@/components/ui/MappedButton",
                    "export_name": "MappedButton",
                }
            }
        }
    }
    result = content_model.build_content_model(
        ast,
        output_dir=str(tmp_path / "sections"),
        page_output=str(tmp_path / "page.tsx"),
        data_output=str(tmp_path / "page.data.ts"),
        root_dir=str(tmp_path),
        component_mapper=mapper,
    )

    hero_file = tmp_path / "sections" / "Hero.tsx"
    hero_code = hero_file.read_text(encoding="utf-8")
    assert 'import MappedButton from "@/components/ui/MappedButton"' in hero_code
    assert "<MappedButton variant=\"Primary\" size=\"Large\" />" in hero_code


def test_data_model_binding_in_section(tmp_path: Path) -> None:
    ast = {
        "root": {
            "tag": "div",
            "children": [
                {
                    "tag": "section",
                    "figma_name": "Features",
                    "classes": [],
                    "children": [
                        {
                            "tag": "div",
                            "data_model": {
                                "model": "Card",
                                "field_map": {"title": "title"},
                                "sample_data": [{"title": "Card A"}],
                            },
                            "children": [
                                {"tag": "h3", "text": "Card A", "data_binding": {"field": "title"}, "classes": []},
                            ],
                        }
                    ],
                }
            ],
        }
    }
    result = content_model.build_content_model(
        ast,
        output_dir=str(tmp_path / "sections"),
        page_output=str(tmp_path / "page.tsx"),
        data_output=str(tmp_path / "page.data.ts"),
        content_model_output=str(tmp_path / "content_model.json"),
        root_dir=str(tmp_path),
    )
    features_file = tmp_path / "sections" / "Features.tsx"
    features_code = features_file.read_text(encoding="utf-8")
    assert "{props.cardData.map((item) => (" in features_code
    assert "{item.title}" in features_code
    assert "cardData?: any[]" in features_code

    data_file = tmp_path / "page.data.ts"
    data_code = data_file.read_text(encoding="utf-8")
    assert "cardData" in data_code
    assert result.data["Features"]["cardData"] == [{"title": "Card A"}]

    cm_file = tmp_path / "content_model.json"
    cm = json.loads(cm_file.read_text(encoding="utf-8"))
    features_section = next(s for s in cm["sections"] if s["name"] == "Features")
    card_field = next(f for f in features_section["fields"] if f["name"] == "cardData")
    assert card_field["type"] == "list"
    assert card_field["label"] == "Card items"
    assert card_field["role"].endswith("Data")


def test_alt_binding_on_data_bound_image(tmp_path: Path) -> None:
    ast = {
        "root": {
            "tag": "div",
            "children": [
                {
                    "tag": "section",
                    "figma_name": "Features",
                    "classes": [],
                    "children": [
                        {
                            "tag": "div",
                            "data_model": {
                                "model": "FeatureCard",
                                "field_map": {"title": "title", "imageUrl": "imageUrl", "imageAlt": "imageAlt"},
                                "sample_data": [
                                    {"title": "Card A", "imageUrl": "/public/assets/enriched/card_a.jpg", "imageAlt": "Card A photo"},
                                ],
                            },
                            "children": [
                                {
                                    "tag": "img",
                                    "classes": ["w-full"],
                                    "data_binding": {"field": "imageUrl"},
                                    "alt_binding": {"field": "imageAlt"},
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    }
    result = content_model.build_content_model(
        ast,
        output_dir=str(tmp_path / "sections"),
        page_output=str(tmp_path / "page.tsx"),
        data_output=str(tmp_path / "page.data.ts"),
        content_model_output=str(tmp_path / "content_model.json"),
        root_dir=str(tmp_path),
    )
    features_file = tmp_path / "sections" / "Features.tsx"
    features_code = features_file.read_text(encoding="utf-8")
    assert "src={item.imageUrl}" in features_code
    assert "alt={item.imageAlt}" in features_code
    assert "Card A photo" in result.data["Features"]["featurecardData"][0]["imageAlt"]
