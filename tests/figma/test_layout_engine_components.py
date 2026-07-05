"""Tests for component/variant tagging in layout_engine.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
LAYOUT_PATH = ROOT / "figma-agent-core" / "layout_engine.py"
REGISTRY_PATH = ROOT / "figma-agent-core" / "component_registry.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_layout_module() -> Any:
    spec = importlib.util.spec_from_file_location("figma_layout_engine", str(LAYOUT_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_layout_engine"] = module
    spec.loader.exec_module(module)
    return module


def _load_registry_module() -> Any:
    spec = importlib.util.spec_from_file_location("figma_component_registry", str(REGISTRY_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_component_registry"] = module
    spec.loader.exec_module(module)
    return module


layout_module = _load_layout_module()
registry_module = _load_registry_module()


def _load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _find_ast_node(root: Any, figma_id: str) -> Any:
    if isinstance(root, dict):
        if root.get("figma_id") == figma_id:
            return root
        for child in root.get("children", []):
            found = _find_ast_node(child, figma_id)
            if found:
                return found
    return None


def test_layout_tags_instance_with_component_ref() -> None:
    doc = _load_fixture("component_set.json")
    registry_data = registry_module.RegistryBuilder(doc).build()

    engine = layout_module.FigmaLayoutEngine({"component_registry": registry_data})
    card_node = next(n for n in doc["children"] if n["name"] == "Card")
    result = engine.convert(card_node)
    root = result.to_dict()["root"]

    instance = _find_ast_node(root, "30:2")
    assert instance is not None
    assert instance.get("is_instance") is True
    assert instance.get("component_ref") == "Button"
    assert instance.get("variant_props") == {"Variant": "Primary", "Size": "Large"}


def test_layout_tags_icon_instance() -> None:
    doc = _load_fixture("component_set.json")
    registry_data = registry_module.RegistryBuilder(doc).build()

    engine = layout_module.FigmaLayoutEngine({"component_registry": registry_data})
    card_node = next(n for n in doc["children"] if n["name"] == "Card")
    result = engine.convert(card_node)
    root = result.to_dict()["root"]

    instance = _find_ast_node(root, "30:3")
    assert instance is not None
    assert instance.get("is_instance") is True
    assert instance.get("component_ref") == "IconButton"


def test_layout_tags_instance_with_figma_component_key() -> None:
    doc = _load_fixture("component_set.json")
    doc["children"][0]["key"] = "figma-button-key"
    registry_data = registry_module.RegistryBuilder(doc).build()

    engine = layout_module.FigmaLayoutEngine({"component_registry": registry_data})
    card_node = next(n for n in doc["children"] if n["name"] == "Card")
    result = engine.convert(card_node)
    root = result.to_dict()["root"]

    instance = _find_ast_node(root, "30:2")
    assert instance is not None
    assert instance.get("figma_component_key") == "figma-button-key"


def test_layout_skips_children_for_mapped_instance() -> None:
    doc = _load_fixture("component_set.json")
    registry_data = registry_module.RegistryBuilder(doc).build()

    engine = layout_module.FigmaLayoutEngine({"component_registry": registry_data})
    card_node = next(n for n in doc["children"] if n["name"] == "Card")
    result = engine.convert(card_node)
    root = result.to_dict()["root"]

    instance = _find_ast_node(root, "30:2")
    assert instance is not None
    assert instance.get("is_instance") is True
    assert not instance.get("children")
