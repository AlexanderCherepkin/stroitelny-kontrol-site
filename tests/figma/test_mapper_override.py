"""Unit tests for figma-agent-core/mapper_override.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
OVERRIDE_PATH = ROOT / "figma-agent-core" / "mapper_override.py"
REGISTRY_PATH = ROOT / "figma-agent-core" / "component_registry.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_override_module() -> Any:
    spec = importlib.util.spec_from_file_location("figma_mapper_override", str(OVERRIDE_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_mapper_override"] = module
    spec.loader.exec_module(module)
    return module


def _load_registry_module() -> Any:
    spec = importlib.util.spec_from_file_location("figma_component_registry", str(REGISTRY_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_component_registry"] = module
    spec.loader.exec_module(module)
    return module


override_module = _load_override_module()
registry_module = _load_registry_module()


def _load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_load_missing_override_returns_empty() -> None:
    override_set = override_module.load_override_set("/nonexistent/path.json")
    assert override_set.rules == []


def test_override_matches_by_component_id() -> None:
    rule = override_module.OverrideRule(
        figma_component_id="10:1",
        react_component={"export_name": "MyButton", "import_path": "@/components/ui/MyButton"},
    )
    assert rule.matches("10:1", "key-a", "Button")
    assert not rule.matches("20:1", "key-a", "Button")


def test_override_matches_by_component_key() -> None:
    rule = override_module.OverrideRule(
        figma_component_key="key-a",
        react_component={"export_name": "MyButton", "import_path": "@/components/ui/MyButton"},
    )
    assert rule.matches("10:1", "key-a", "Button")
    assert not rule.matches("10:1", "key-b", "Button")


def test_disabled_rule_never_matches() -> None:
    rule = override_module.OverrideRule(
        figma_component_id="10:1",
        react_component={"export_name": "MyButton", "import_path": "@/components/ui/MyButton"},
        disabled=True,
    )
    assert not rule.matches("10:1", "key-a", "Button")


def test_validate_override_catches_missing_identifier() -> None:
    rule = override_module.OverrideRule(react_component={"export_name": "X", "import_path": "@/x"})
    issues = override_module.validate_override_set(override_module.OverrideSet(rules=[rule]))
    assert any("no figma_component" in issue.lower() for issue in issues)


def test_validate_override_catches_missing_export_name() -> None:
    rule = override_module.OverrideRule(
        figma_component_id="10:1",
        react_component={"import_path": "@/x"},
    )
    issues = override_module.validate_override_set(override_module.OverrideSet(rules=[rule]))
    assert any("export_name" in issue for issue in issues)


def test_validate_override_catches_unknown_local_component() -> None:
    rule = override_module.OverrideRule(
        figma_component_id="10:1",
        react_component={"export_name": "Unknown", "import_path": "@/x"},
    )
    issues = override_module.validate_override_set(
        override_module.OverrideSet(rules=[rule]), local_export_names={"Button"}
    )
    assert any("not found in local components" in issue for issue in issues)


def test_apply_override_sets_reuse_action_and_react_component() -> None:
    mapping = {
        "figma_component_id": "10:1",
        "action": "generate",
        "react_component": {"export_name": "Button", "import_path": "./Button"},
    }
    rule = override_module.OverrideRule(
        figma_component_id="10:1",
        react_component={"export_name": "ShadcnButton", "import_path": "@/components/ui/button"},
        reason="use existing shadcn button",
    )
    merged = override_module.apply_override(mapping, rule)
    assert merged["action"] == "reuse"
    assert merged["react_component"]["export_name"] == "ShadcnButton"
    assert merged["manual_override"]["reason"] == "use existing shadcn button"


def test_merge_overrides_into_mapper_rewrites_matching_entry(tmp_path: Path) -> None:
    mapper = {
        "version": "1.0",
        "mappings": {
            "10:1": {
                "figma_component_id": "10:1",
                "figma_name": "Button",
                "action": "generate",
                "react_component": {"export_name": "Button", "import_path": "./Button"},
            },
            "20:1": {
                "figma_component_id": "20:1",
                "figma_name": "IconButton",
                "action": "generate",
                "react_component": {"export_name": "IconButton", "import_path": "./IconButton"},
            },
        },
    }
    override_set = override_module.OverrideSet(
        rules=[
            override_module.OverrideRule(
                figma_component_id="10:1",
                react_component={"export_name": "ShadcnButton", "import_path": "@/components/ui/button"},
            )
        ]
    )
    merged = override_module.merge_overrides_into_mapper(mapper, override_set)
    assert merged["mappings"]["10:1"]["react_component"]["export_name"] == "ShadcnButton"
    assert merged["mappings"]["20:1"]["react_component"]["export_name"] == "IconButton"


def test_merge_overrides_matches_by_name_when_id_missing(tmp_path: Path) -> None:
    mapper = {
        "version": "1.0",
        "mappings": {
            "10:1": {
                "figma_component_id": "10:1",
                "figma_name": "Button",
                "action": "generate",
                "react_component": {"export_name": "Button", "import_path": "./Button"},
            },
        },
    }
    override_set = override_module.OverrideSet(
        rules=[
            override_module.OverrideRule(
                figma_name="Button",
                react_component={"export_name": "ShadcnButton", "import_path": "@/components/ui/button"},
            )
        ]
    )
    merged = override_module.merge_overrides_into_mapper(mapper, override_set)
    assert merged["mappings"]["10:1"]["react_component"]["export_name"] == "ShadcnButton"


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "overrides.json"
    override_set = override_module.OverrideSet(
        rules=[
            override_module.OverrideRule(
                figma_component_id="10:1",
                react_component={"export_name": "Button", "import_path": "@/components/ui/button"},
                reason="reuse",
            )
        ]
    )
    override_module.save_override_set(path, override_set)
    loaded = override_module.load_override_set(path)
    assert len(loaded.rules) == 1
    assert loaded.rules[0].figma_component_id == "10:1"
    assert loaded.rules[0].react_component["export_name"] == "Button"


def test_add_override_replaces_duplicate(tmp_path: Path) -> None:
    path = tmp_path / "overrides.json"
    override_module.add_override(
        path,
        figma_component_id="10:1",
        react_component={"export_name": "Button", "import_path": "@/a"},
    )
    override_module.add_override(
        path,
        figma_component_id="10:1",
        react_component={"export_name": "Button2", "import_path": "@/b"},
    )
    loaded = override_module.load_override_set(path)
    assert len(loaded.rules) == 1
    assert loaded.rules[0].react_component["export_name"] == "Button2"


def test_component_registry_build_and_write_applies_override(tmp_path: Path) -> None:
    doc = _load_fixture("component_set.json")
    override_path = tmp_path / "overrides.json"
    override_module.save_override_set(
        override_path,
        override_module.OverrideSet(
            rules=[
                override_module.OverrideRule(
                    figma_component_id="10:1",
                    react_component={"export_name": "ShadcnButton", "import_path": "@/components/ui/button"},
                    prop_mapping={"Variant": "variant", "Size": "size"},
                    value_mapping={"variant": {"Primary": "primary", "Secondary": "secondary"}},
                    default_props={"variant": "primary"},
                    reason="reuse shadcn",
                )
            ]
        ),
    )
    builder = registry_module.RegistryBuilder(
        doc,
        output_path=tmp_path / "registry.json",
        mapper_output_path=tmp_path / "figma_component_map.json",
        per_component_mapper_dir=tmp_path / "__mappers__",
        aggregate_mapper_path=tmp_path / "figma_component_mappings.json",
        override_path=override_path,
    )
    builder.build_and_write()
    aggregate = json.loads((tmp_path / "figma_component_mappings.json").read_text(encoding="utf-8"))
    button_mapping = aggregate["mappings"]["10:1"]
    assert button_mapping["action"] == "reuse"
    assert button_mapping["react_component"]["export_name"] == "ShadcnButton"
    assert button_mapping["manual_override"]["reason"] == "reuse shadcn"
    assert button_mapping["prop_mapping"] == {"Variant": "variant", "Size": "size"}
    assert button_mapping["default_props"] == {"variant": "primary"}


def test_component_registry_load_with_overrides(tmp_path: Path) -> None:
    doc = _load_fixture("component_set.json")
    builder = registry_module.RegistryBuilder(
        doc,
        output_path=tmp_path / "registry.json",
        mapper_output_path=tmp_path / "figma_component_map.json",
        aggregate_mapper_path=tmp_path / "figma_component_mappings.json",
    )
    builder.build_and_write()

    override_path = tmp_path / "overrides.json"
    override_module.save_override_set(
        override_path,
        override_module.OverrideSet(
            rules=[
                override_module.OverrideRule(
                    figma_component_id="10:1",
                    react_component={"export_name": "ShadcnButton", "import_path": "@/components/ui/button"},
                )
            ]
        ),
    )

    reg = registry_module.ComponentRegistry.load_with_per_component_mappers(
        tmp_path / "registry.json",
        aggregate_mapper_path=tmp_path / "figma_component_mappings.json",
        override_path=override_path,
    )
    mapping = reg.lookup_mapping("10:1")
    assert mapping is not None
    assert mapping["react_component"]["export_name"] == "ShadcnButton"


def test_layout_engine_applies_override_to_instance(tmp_path: Path) -> None:
    doc = _load_fixture("component_set.json")
    builder = registry_module.RegistryBuilder(
        doc,
        output_path=tmp_path / "registry.json",
        mapper_output_path=tmp_path / "figma_component_map.json",
        aggregate_mapper_path=tmp_path / "figma_component_mappings.json",
    )
    builder.build_and_write()

    override_path = tmp_path / "overrides.json"
    override_module.save_override_set(
        override_path,
        override_module.OverrideSet(
            rules=[
                override_module.OverrideRule(
                    figma_component_id="10:1",
                    react_component={"export_name": "ShadcnButton", "import_path": "@/components/ui/button"},
                    prop_mapping={"Variant": "variant", "Size": "size"},
                    value_mapping={"variant": {"Primary": "primary", "Secondary": "secondary"}, "size": {"Small": "sm", "Large": "lg"}},
                    default_props={"variant": "primary"},
                )
            ]
        ),
    )

    layout_mod = _load_layout_engine_module()
    config = {
        "component_registry": str(tmp_path / "registry.json"),
        "component_mapper": str(tmp_path / "figma_component_map.json"),
        "component_mapper_override": str(override_path),
    }
    engine = layout_mod.FigmaLayoutEngine(config=config)
    instance_node = {
        "id": "30:2",
        "type": "INSTANCE",
        "componentSetId": "10:1",
        "componentId": "11:1",
        "variantProperties": {"Variant": "Secondary", "Size": "Large"},
    }
    ast = engine.convert(instance_node)
    assert ast.root.component_ref == "ShadcnButton"
    assert ast.root.variant_props == {"variant": "secondary", "size": "lg"}


def _load_layout_engine_module() -> Any:
    path = ROOT / "figma-agent-core" / "layout_engine.py"
    spec = importlib.util.spec_from_file_location("figma_layout_engine", str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_layout_engine"] = module
    spec.loader.exec_module(module)
    return module
