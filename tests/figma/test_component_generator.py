"""Unit tests for ComponentGenerator in figma-agent-core/component_extractor.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
EXTRACTOR_PATH = ROOT / "figma-agent-core" / "component_extractor.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_extractor_module() -> Any:
    spec = importlib.util.spec_from_file_location("figma_component_extractor", str(EXTRACTOR_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_component_extractor"] = module
    spec.loader.exec_module(module)
    return module


extractor = _load_extractor_module()


def _load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_generator_creates_registry_and_files(tmp_path: Path) -> None:
    doc = _load_fixture("component_set.json")
    gen = extractor.ComponentGenerator(
        doc,
        output_dir=str(tmp_path / "ui"),
        root_dir=str(tmp_path),
    )
    registry, components = gen.generate()

    assert "10:1" in registry["components"]
    names = [c.name for c in components]
    assert "Button" in names
    assert "IconButton" in names
    assert (tmp_path / "ui" / "Button.tsx").exists()
    assert (tmp_path / "ui" / "IconButton.tsx").exists()


def test_generated_button_has_interface_and_props(tmp_path: Path) -> None:
    doc = _load_fixture("component_set.json")
    gen = extractor.ComponentGenerator(
        doc,
        output_dir=str(tmp_path / "ui"),
        root_dir=str(tmp_path),
    )
    _, components = gen.generate()
    button = next(c for c in components if c.name == "Button")
    code = button.file_path.read_text(encoding="utf-8")

    assert "export interface ButtonProps" in code
    assert "variant?: \"Primary\" | \"Secondary\"" in code or "variant?:" in code
    assert "size?: \"Small\" | \"Large\"" in code or "size?:" in code
    assert "className?: string" in code
    assert "export default function Button(props: ButtonProps)" in code


def test_generated_button_includes_text_override_prop(tmp_path: Path) -> None:
    doc = _load_fixture("component_set.json")
    gen = extractor.ComponentGenerator(
        doc,
        output_dir=str(tmp_path / "ui"),
        root_dir=str(tmp_path),
    )
    _, components = gen.generate()
    button = next(c for c in components if c.name == "Button")
    code = button.file_path.read_text(encoding="utf-8")

    assert "label?: string" in code
    assert "props.label" in code


def test_generator_orders_dependencies_before_dependents(tmp_path: Path) -> None:
    doc = _load_fixture("component_set.json")
    gen = extractor.ComponentGenerator(
        doc,
        output_dir=str(tmp_path / "ui"),
        root_dir=str(tmp_path),
    )
    registry, _ = gen.generate()
    order = registry["dependency_order"]
    for entry_id, entry in registry["components"].items():
        for dep in entry.get("dependencies", []):
            assert order.index(dep) < order.index(entry_id)
