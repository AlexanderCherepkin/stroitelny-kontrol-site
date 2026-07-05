"""Unit tests for Component Mapping: Figma component key → React component + props."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY_PATH = ROOT / "figma-agent-core" / "component_registry.py"


def _load_registry_module() -> Any:
    spec = importlib.util.spec_from_file_location("figma_component_registry_v2", str(REGISTRY_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_component_registry_v2"] = module
    spec.loader.exec_module(module)
    return module


registry_module = _load_registry_module()


def test_mapper_builds_prop_mapping_from_schema() -> None:
    doc = {
        "id": "0:1",
        "name": "Page",
        "type": "DOCUMENT",
        "children": [
            {
                "id": "10:1",
                "name": "Button",
                "type": "COMPONENT_SET",
                "variantGroupProperties": {
                    "Variant": {
                        "type": "STRING",
                        "values": ["Primary", "Secondary"],
                        "defaultValue": "Primary",
                    },
                    "Size": {
                        "type": "STRING",
                        "values": ["Small", "Large"],
                        "defaultValue": "Small",
                    },
                },
                "children": [
                    {
                        "id": "11:1",
                        "name": "Primary / Small",
                        "type": "COMPONENT",
                        "componentSetId": "10:1",
                        "variantProperties": {"Variant": "Primary", "Size": "Small"},
                    }
                ],
            }
        ],
    }
    builder = registry_module.RegistryBuilder(doc)
    registry = builder.build()
    mapper = registry_module.ComponentMapper(registry)
    data = mapper.build()

    assert "10:1" in data["mappings"]
    mapping = data["mappings"]["10:1"]
    assert mapping["figma_name"] == "Button"
    assert mapping["prop_mapping"] == {"Variant": "variant", "Size": "size"}
    assert mapping["value_mapping"]["variant"] == {"Primary": "primary", "Secondary": "secondary"}
    assert mapping["value_mapping"]["size"] == {"Small": "small", "Large": "large"}
    assert mapping["default_props"] == {"variant": "primary", "size": "small"}


def test_mapper_parses_slash_separated_variant_names() -> None:
    doc = {
        "id": "0:1",
        "name": "Page",
        "type": "DOCUMENT",
        "children": [
            {
                "id": "10:1",
                "name": "Button",
                "type": "COMPONENT_SET",
                "children": [
                    {
                        "id": "11:1",
                        "name": "Primary / Large / Filled",
                        "type": "COMPONENT",
                        "componentSetId": "10:1",
                    },
                    {
                        "id": "12:1",
                        "name": "Secondary / Small / Outlined",
                        "type": "COMPONENT",
                        "componentSetId": "10:1",
                    },
                ],
            }
        ],
    }
    builder = registry_module.RegistryBuilder(doc)
    registry = builder.build()
    mapper = registry_module.ComponentMapper(registry)
    data = mapper.build()

    mapping = data["mappings"]["10:1"]
    assert mapping["value_mapping"]["prop1"] == {
        "Primary": "primary",
        "Secondary": "secondary",
    }
    assert mapping["value_mapping"]["prop2"] == {"Large": "large", "Small": "small"}
    assert mapping["value_mapping"]["prop3"] == {"Filled": "filled", "Outlined": "outlined"}


def test_mapper_reuse_uses_local_component_path() -> None:
    doc = {
        "id": "0:1",
        "name": "Page",
        "type": "DOCUMENT",
        "children": [
            {
                "id": "10:1",
                "name": "Button",
                "type": "COMPONENT_SET",
                "variantGroupProperties": {
                    "Variant": {
                        "type": "STRING",
                        "values": ["Primary", "Secondary"],
                        "defaultValue": "Primary",
                    }
                },
                "children": [
                    {
                        "id": "11:1",
                        "name": "Primary",
                        "type": "COMPONENT",
                        "componentSetId": "10:1",
                        "variantProperties": {"Variant": "Primary"},
                    }
                ],
            }
        ],
    }
    builder = registry_module.RegistryBuilder(doc)
    registry = builder.build()
    registry["component_decisions"] = {
        "10:1": {
            "action": "reuse",
            "reason": "Local match",
            "local_match": {
                "file_path": "src/components/ui/Button.tsx",
                "export_name": "Button",
                "props": {"variant": "string"},
            },
        }
    }
    mapper = registry_module.ComponentMapper(registry)
    data = mapper.build()

    mapping = data["mappings"]["10:1"]
    assert mapping["action"] == "reuse"
    assert mapping["react_component"]["import_path"] == "@/components/ui/Button"
    assert mapping["react_component"]["export_name"] == "Button"
    assert mapping["react_component"]["file_path"] == "src/components/ui/Button.tsx"


def test_mapper_generate_uses_generated_component_path() -> None:
    doc = {
        "id": "0:1",
        "name": "Page",
        "type": "DOCUMENT",
        "children": [
            {
                "id": "10:1",
                "name": "Button",
                "type": "COMPONENT_SET",
                "children": [
                    {
                        "id": "11:1",
                        "name": "Primary",
                        "type": "COMPONENT",
                        "componentSetId": "10:1",
                    }
                ],
            }
        ],
    }
    builder = registry_module.RegistryBuilder(doc)
    registry = builder.build()
    mapper = registry_module.ComponentMapper(registry)
    data = mapper.build()

    mapping = data["mappings"]["10:1"]
    assert mapping["action"] == "generate"
    assert mapping["react_component"]["import_path"] == "./Button"
    assert mapping["react_component"]["export_name"] == "Button"
    assert mapping["react_component"]["file_path"] == "src/components/ui/Button.tsx"


def test_props_for_instance_translates_variants() -> None:
    mapping = {
        "prop_mapping": {"Variant": "variant", "Size": "size"},
        "value_mapping": {
            "variant": {"Primary": "primary", "Secondary": "secondary"},
            "size": {"Large": "large", "Small": "small"},
        },
        "default_props": {"variant": "primary", "size": "small"},
    }
    props = registry_module.ComponentMapper.props_for_instance(
        mapping, {"Variant": "Secondary", "Size": "Large"}
    )
    assert props == {"variant": "secondary", "size": "large"}


def test_props_for_instance_fills_defaults() -> None:
    mapping = {
        "prop_mapping": {"Variant": "variant"},
        "value_mapping": {"variant": {"Primary": "primary"}},
        "default_props": {"variant": "primary"},
    }
    props = registry_module.ComponentMapper.props_for_instance(mapping, {})
    assert props == {"variant": "primary"}


def test_props_for_instance_reads_variant_prop_map() -> None:
    mapping = {
        "variant_prop_map": {"Variant": "variant", "Size": "size"},
        "value_mapping": {
            "variant": {"Primary": "primary"},
            "size": {"Large": "large"},
        },
        "default_props": {"size": "small"},
    }
    props = registry_module.ComponentMapper.props_for_instance(
        mapping, {"Variant": "Primary", "Size": "Large"}
    )
    assert props == {"variant": "primary", "size": "large"}


def test_registry_builder_writes_mapper_file(tmp_path: Path) -> None:
    doc = {
        "id": "0:1",
        "name": "Page",
        "type": "DOCUMENT",
        "children": [
            {
                "id": "10:1",
                "name": "Button",
                "type": "COMPONENT_SET",
                "children": [
                    {
                        "id": "11:1",
                        "name": "Primary / Small",
                        "type": "COMPONENT",
                        "componentSetId": "10:1",
                    }
                ],
            }
        ],
    }
    registry_path = tmp_path / "registry.json"
    mapper_path = tmp_path / "mapper.json"
    builder = registry_module.RegistryBuilder(doc, output_path=registry_path, mapper_output_path=mapper_path)
    builder.build_and_write()

    assert mapper_path.exists()
    data = json.loads(mapper_path.read_text(encoding="utf-8"))
    assert "mappings" in data
    assert "10:1" in data["mappings"]


def test_mapper_includes_component_key_and_doc_fields() -> None:
    doc = {
        "id": "0:1",
        "name": "Page",
        "type": "DOCUMENT",
        "children": [
            {
                "id": "10:1",
                "name": "Button",
                "type": "COMPONENT_SET",
                "key": "figma-button-key",
                "description": "Call to action",
                "variantGroupProperties": {
                    "Variant": {
                        "type": "STRING",
                        "values": ["Primary"],
                        "defaultValue": "Primary",
                    }
                },
                "children": [
                    {
                        "id": "11:1",
                        "name": "Primary",
                        "type": "COMPONENT",
                        "componentSetId": "10:1",
                    }
                ],
            }
        ],
    }
    builder = registry_module.RegistryBuilder(doc)
    registry = builder.build()
    mapper = registry_module.ComponentMapper(registry)
    data = mapper.build()

    mapping = data["mappings"]["10:1"]
    assert mapping["figma_component_key"] == "figma-button-key"
    assert mapping["pascal_name"] == "Button"
    assert mapping["description"] == "Call to action"
    assert mapping["doc_url"] == "src/components/ui/Button.tsx"


def test_registry_builder_writes_per_component_and_aggregate_mappers(tmp_path: Path) -> None:
    doc = {
        "id": "0:1",
        "name": "Page",
        "type": "DOCUMENT",
        "children": [
            {
                "id": "10:1",
                "name": "Button",
                "type": "COMPONENT_SET",
                "children": [
                    {
                        "id": "11:1",
                        "name": "Primary",
                        "type": "COMPONENT",
                        "componentSetId": "10:1",
                    }
                ],
            }
        ],
    }
    registry_path = tmp_path / "registry.json"
    mapper_path = tmp_path / "mapper.json"
    per_component_dir = tmp_path / "mappers"
    aggregate_path = tmp_path / "figma_component_mappings.json"
    builder = registry_module.RegistryBuilder(
        doc,
        output_path=registry_path,
        mapper_output_path=mapper_path,
        per_component_mapper_dir=per_component_dir,
        aggregate_mapper_path=aggregate_path,
    )
    builder.build_and_write()

    assert aggregate_path.exists()
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    assert aggregate["mappings"]["10:1"]["pascal_name"] == "Button"

    per_component_file = per_component_dir / "Button.mapper.json"
    assert per_component_file.exists()
    per_component = json.loads(per_component_file.read_text(encoding="utf-8"))
    assert per_component["figma_component_id"] == "10:1"
    assert per_component["react_component"]["export_name"] == "Button"
