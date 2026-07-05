"""Unit tests for figma-agent-core/interactive_layer_mapper.py.

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
MAPPER_PATH = ROOT / "figma-agent-core" / "interactive_layer_mapper.py"


def _load_mapper() -> Any:
    spec = importlib.util.spec_from_file_location("figma_interactive_mapper", str(MAPPER_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_interactive_mapper"] = module
    spec.loader.exec_module(module)
    return module


mapper = _load_mapper()


def _minimal_figma_node(node_id: str, name: str, reactions: list | None = None, children: list | None = None) -> dict:
    return {
        "id": node_id,
        "name": name,
        "reactions": reactions or [],
        "children": children or [],
    }


def _minimal_ast(figma_id: str, tag: str = "div", children: list | None = None) -> dict:
    return {
        "figma_id": figma_id,
        "tag": tag,
        "children": children or [],
    }


def test_load_module() -> None:
    assert hasattr(mapper, "map_interactions")
    assert hasattr(mapper, "run_mapping")


def test_navigation_interaction() -> None:
    figma = _minimal_figma_node(
        "1:2",
        "Hero CTA",
        reactions=[
            {
                "trigger": {"type": "ON_CLICK"},
                "action": {"type": "NODE", "destinationId": "10:20", "navigationType": "NAVIGATE"},
            }
        ],
    )
    dest = _minimal_figma_node("10:20", "Pricing Page")
    figma["children"].append(dest)

    ast = _minimal_ast("1:2", "button")

    result = mapper.map_interactions(figma, ast)
    registry = result["registry"]
    assert len(registry["interactions"]) == 1
    interaction = registry["interactions"][0]
    assert interaction["figma_id"] == "1:2"
    assert interaction["state_key"] == "HeroCtaState"
    assert interaction["triggers"][0]["type"] == "navigate"
    assert interaction["triggers"][0]["route"] == "/pricing_page"
    assert "/pricing_page" in registry["routes"]


def test_overlay_interaction() -> None:
    figma = _minimal_figma_node(
        "1:2",
        "Open Modal",
        reactions=[
            {
                "trigger": {"type": "ON_CLICK"},
                "action": {"type": "OVERLAY", "destinationId": "5:6", "overlayPositionType": "CENTER"},
            }
        ],
    )
    overlay = _minimal_figma_node("5:6", "Modal Overlay")
    figma["children"].append(overlay)

    ast = _minimal_ast("1:2", "div", children=[_minimal_ast("5:6", "div")])

    result = mapper.map_interactions(figma, ast)
    assert len(result["registry"]["interactions"]) == 1
    assert result["registry"]["interactions"][0]["triggers"][0]["type"] == "overlay"


def test_url_interaction_external() -> None:
    figma = _minimal_figma_node(
        "1:2",
        "External Link",
        reactions=[
            {
                "trigger": {"type": "ON_CLICK"},
                "action": {"type": "URL", "url": "https://example.com"},
            }
        ],
    )
    ast = _minimal_ast("1:2", "a")

    result = mapper.map_interactions(figma, ast)
    trigger = result["registry"]["interactions"][0]["triggers"][0]
    assert trigger["type"] == "url"
    assert trigger["external"] is True
    assert trigger["url"] == "https://example.com"


def test_hover_event() -> None:
    figma = _minimal_figma_node(
        "1:2",
        "Hover Button",
        reactions=[
            {
                "trigger": {"type": "ON_HOVER"},
                "action": {"type": "URL", "url": "/hover-target"},
            }
        ],
    )
    ast = _minimal_ast("1:2", "div")

    result = mapper.map_interactions(figma, ast)
    trigger = result["registry"]["interactions"][0]["triggers"][0]
    assert trigger["event"] == "on_hover"


def test_interactive_metadata_attached_to_ast() -> None:
    figma = _minimal_figma_node(
        "1:2",
        "CTA",
        reactions=[
            {
                "trigger": {"type": "ON_CLICK"},
                "action": {"type": "NODE", "destinationId": "10:20"},
            }
        ],
    )
    ast = _minimal_ast("1:2", "button")

    result = mapper.map_interactions(figma, ast)
    assert "interactive" in result["ast"]
    assert result["ast"]["interactive"]["state_key"] == "CTAState"
    assert result["ast"]["interactive"]["needs_client"] is True


def test_run_mapping_writes_files(tmp_path: Path) -> None:
    figma_file = tmp_path / "figma_node.json"
    ast_file = tmp_path / "page_ast.json"
    ast_output = tmp_path / "interactive_ast.json"
    registry_output = tmp_path / "interactive_registry.json"

    figma = _minimal_figma_node(
        "1:2",
        "CTA",
        reactions=[{"trigger": {"type": "ON_CLICK"}, "action": {"type": "URL", "url": "/go"}}],
    )
    ast = _minimal_ast("1:2", "button")

    figma_file.write_text(json.dumps(figma), encoding="utf-8")
    ast_file.write_text(json.dumps(ast), encoding="utf-8")

    mapper.run_mapping(
        figma_file=str(figma_file),
        ast_file=str(ast_file),
        ast_output=str(ast_output),
        registry_output=str(registry_output),
    )

    assert ast_output.exists()
    assert registry_output.exists()
    registry = json.loads(registry_output.read_text(encoding="utf-8"))
    assert len(registry["interactions"]) == 1
    assert registry["state_keys"] == ["CTAState"]
