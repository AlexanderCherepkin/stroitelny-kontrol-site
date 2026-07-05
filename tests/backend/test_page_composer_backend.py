"""Tests for backend rendering in figma-agent-core/page_composer.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
PAGE_COMPOSER_PATH = ROOT / "figma-agent-core" / "page_composer.py"


def _load_page_composer() -> Any:
    spec = importlib.util.spec_from_file_location("page_composer", str(PAGE_COMPOSER_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["page_composer"] = module
    spec.loader.exec_module(module)
    return module


page_composer = _load_page_composer()


def _sample_ast() -> dict[str, Any]:
    return {
        "root": {
            "figma_id": "10:1",
            "figma_name": "Page",
            "tag": "section",
            "classes": ["p-4"],
            "children": [
                {
                    "figma_id": "10:2",
                    "figma_name": "Lead Form",
                    "tag": "form",
                    "classes": ["border", "rounded"],
                    "backend_action": "createLeadAction",
                    "backend_model": "Lead",
                    "children": [
                        {
                            "figma_id": "10:3",
                            "figma_name": "email field",
                            "tag": "input",
                            "classes": ["border", "rounded"],
                            "backend_field": "email",
                            "input_type": "email",
                            "required": True,
                            "text": "Enter your email",
                        },
                    ],
                },
            ],
        }
    }


def test_detect_backend_imports() -> None:
    imports = page_composer._detect_backend_imports(_sample_ast())
    assert 'import { createLeadAction } from "@/app/actions/leadAction"' in imports


def test_node_to_tsx_renders_form_action() -> None:
    ast = _sample_ast()
    form = ast["root"]["children"][0]
    tsx = page_composer._node_to_tsx(form, depth=1)
    assert 'action={lead_formAction}' in tsx
    assert 'onSubmit={handleSubmit_lead_form(() => {})}' in tsx


def test_node_to_tsx_renders_backend_input() -> None:
    ast = _sample_ast()
    form = ast["root"]["children"][0]
    input_node = form["children"][0]
    tsx = page_composer._node_to_tsx(input_node, depth=2, form_key="lead_form")
    assert '<input' in tsx
    assert 'name="email"' in tsx
    assert 'type="email"' in tsx
    assert "required" in tsx
    assert 'placeholder="Enter your email"' in tsx
    assert '{...register_lead_form("email")}' in tsx


def test_compose_page_includes_backend_imports() -> None:
    page = page_composer.compose_page(_sample_ast())
    assert 'import { createLeadAction } from "@/app/actions/leadAction"' in page
    assert 'action={lead_formAction}' in page
    assert 'import { useForm } from "react-hook-form"' in page
    assert 'import { zodResolver } from "@hookform/resolvers/zod"' in page
    assert 'import { useFormState } from "react-dom"' in page
