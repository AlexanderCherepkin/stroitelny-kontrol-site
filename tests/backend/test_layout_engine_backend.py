"""Tests for backend mapping integration in figma-agent-core/layout_engine.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
LAYOUT_ENGINE_PATH = ROOT / "figma-agent-core" / "layout_engine.py"


def _load_layout_engine() -> Any:
    spec = importlib.util.spec_from_file_location("figma_layout_engine", str(LAYOUT_ENGINE_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_layout_engine"] = module
    spec.loader.exec_module(module)
    return module


layout_engine = _load_layout_engine()


def _sample_backend_mapping() -> dict[str, Any]:
    return {
        "mappings": [
            {
                "node_id": "form:1",
                "node_name": "Contact Form",
                "kind": "form",
                "model": "Lead",
                "endpoint": "/api/leads",
                "action": "createLeadAction",
                "confidence": 0.92,
                "field_mappings": [
                    {
                        "node_id": "input:1",
                        "node_name": "Email Input",
                        "field": "email",
                        "type": "email",
                        "required": True,
                        "confidence": 0.95,
                    },
                    {
                        "node_id": "input:2",
                        "node_name": "Name Input",
                        "field": "name",
                        "type": "text",
                        "required": True,
                        "confidence": 0.9,
                    },
                ],
            }
        ]
    }


def test_layout_engine_applies_backend_hints() -> None:
    node = {
        "id": "form:1",
        "name": "Contact Form",
        "type": "FRAME",
        "visible": True,
        "children": [
            {
                "id": "input:1",
                "name": "Email Input",
                "type": "RECTANGLE",
                "visible": True,
                "box": {"x": 0, "y": 0, "width": 200, "height": 40},
            },
            {
                "id": "input:2",
                "name": "Name Input",
                "type": "RECTANGLE",
                "visible": True,
                "box": {"x": 0, "y": 0, "width": 200, "height": 40},
            },
        ],
    }
    result = layout_engine.convert_figma_node(node, config={"backend_mapping": _sample_backend_mapping()})
    root = result.root
    assert root.backend_action == "createLeadAction"
    assert root.backend_model == "Lead"
    assert root.backend_endpoint == "/api/leads"
    email_node = next(c for c in root.children if c.figma_id == "input:1")
    assert email_node.backend_field == "email"
    assert email_node.input_type == "email"
    assert email_node.required is True
    name_node = next(c for c in root.children if c.figma_id == "input:2")
    assert name_node.backend_field == "name"
    assert name_node.input_type == "text"
