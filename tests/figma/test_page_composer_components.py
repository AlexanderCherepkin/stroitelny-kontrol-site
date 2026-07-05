"""Tests for instance rendering in page_composer.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
PAGE_COMPOSER_PATH = ROOT / "figma-agent-core" / "page_composer.py"


def _load_page_composer() -> Any:
    spec = importlib.util.spec_from_file_location("figma_page_composer", str(PAGE_COMPOSER_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_page_composer"] = module
    spec.loader.exec_module(module)
    return module


page_composer = _load_page_composer()


def _minimal_ast_with_instance() -> Any:
    return {
        "root": {
            "tag": "section",
            "figma_id": "0:1",
            "figma_name": "Page",
            "children": [
                {
                    "tag": "div",
                    "figma_id": "30:1",
                    "figma_name": "Card",
                    "classes": ["flex", "flex-col"],
                    "children": [
                        {
                            "tag": "button",
                            "figma_id": "30:2",
                            "figma_name": "Card Button",
                            "figma_type": "INSTANCE",
                            "component_ref": "Button",
                            "is_instance": True,
                            "variant_props": {"Variant": "Primary", "Size": "Large"},
                            "classes": [],
                        }
                    ],
                }
            ],
        }
    }


def test_compose_renders_instance_as_component() -> None:
    ast = _minimal_ast_with_instance()
    code = page_composer.compose_page(ast, title="Test")

    assert 'import Button from "@/components/ui/Button"' in code
    assert "<Button variant=\"Primary\" size=\"Large\" />" in code


def test_compose_skips_component_context_definitions() -> None:
    ast = {
        "root": {
            "tag": "section",
            "figma_id": "0:1",
            "figma_name": "Page",
            "children": [
                {
                    "tag": "div",
                    "figma_id": "10:1",
                    "figma_name": "Button",
                    "figma_type": "COMPONENT_SET",
                    "component_context": "Button",
                    "classes": ["hidden"],
                    "children": [],
                },
                {
                    "tag": "button",
                    "figma_id": "30:2",
                    "figma_name": "Instance",
                    "figma_type": "INSTANCE",
                    "component_ref": "Button",
                    "is_instance": True,
                    "variant_props": {"Variant": "Primary"},
                    "classes": [],
                },
            ],
        }
    }
    code = page_composer.compose_page(ast, title="Test")
    assert 'import Button from "@/components/ui/Button"' in code
    assert "<Button variant=\"Primary\" />" in code
    assert "<div className=\"hidden\">" not in code


def test_compose_uses_mapper_import_path_and_props() -> None:
    ast = _minimal_ast_with_instance()
    ast["root"]["children"][0]["children"][0]["component_set_id"] = "10:1"
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
    code = page_composer.compose_page(ast, title="Test", component_mapper=mapper)
    assert 'import MappedButton from "@/components/ui/MappedButton"' in code
    assert "<MappedButton variant=\"Primary\" size=\"Large\" />" in code
