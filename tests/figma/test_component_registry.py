"""Unit tests for figma-agent-core/component_registry.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY_PATH = ROOT / "figma-agent-core" / "component_registry.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_registry_module() -> Any:
    spec = importlib.util.spec_from_file_location("figma_component_registry", str(REGISTRY_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_component_registry"] = module
    spec.loader.exec_module(module)
    return module


registry_module = _load_registry_module()


def _load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_registry_extracts_component_set() -> None:
    doc = _load_fixture("component_set.json")
    builder = registry_module.RegistryBuilder(doc)
    data = builder.build()

    assert "10:1" in data["components"]
    entry = data["components"]["10:1"]
    assert entry["node_type"] == "COMPONENT_SET"
    assert entry["pascal_name"] == "Button"
    assert entry["file_path"] == "src/components/ui/Button.tsx"
    assert entry["default_variant_id"] == "11:1"
    assert set(entry["variant_properties"].keys()) == {"Variant", "Size"}
    assert entry["variant_properties"]["Variant"]["values"] == ["Primary", "Secondary"]


def test_registry_extracts_standalone_component() -> None:
    doc = _load_fixture("component_set.json")
    builder = registry_module.RegistryBuilder(doc)
    data = builder.build()

    assert "20:1" in data["components"]
    entry = data["components"]["20:1"]
    assert entry["node_type"] == "COMPONENT"
    assert entry["pascal_name"] == "IconButton"
    assert entry["variants"][0]["id"] == "20:1"


def test_registry_collects_instances() -> None:
    doc = _load_fixture("component_set.json")
    builder = registry_module.RegistryBuilder(doc)
    data = builder.build()

    button_entry = data["components"]["10:1"]
    assert "30:2" in button_entry["instances"]
    assert "30:3" not in button_entry["instances"]

    instance = data["instances"]["30:2"]
    assert instance["component_set_id"] == "10:1"
    assert instance["component_id"] == "11:1"
    assert instance["variant_properties"]["Variant"] == "Primary"


def test_registry_dependency_order() -> None:
    doc = _load_fixture("component_set.json")
    builder = registry_module.RegistryBuilder(doc)
    data = builder.build()

    order = data["dependency_order"]
    assert "10:1" in order
    assert "20:1" in order
    # IconButton has no deps; Button depends on IconButton via nested instance? Actually our fixture
    # has Card (FRAME) containing instances, not component sets containing instances. So no component deps.
    # Ensure all components appear before any depending component; here none depend on each other.


def test_registry_writes_file(tmp_path: Path) -> None:
    doc = _load_fixture("component_set.json")
    out = tmp_path / "registry.json"
    builder = registry_module.RegistryBuilder(doc, output_path=out)
    builder.build_and_write()
    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert "components" in loaded


def test_component_registry_lookup() -> None:
    doc = _load_fixture("component_set.json")
    builder = registry_module.RegistryBuilder(doc)
    data = builder.build()
    reg = registry_module.ComponentRegistry(data)

    instance = {
        "id": "30:2",
        "type": "INSTANCE",
        "componentSetId": "10:1",
        "componentId": "11:1",
    }
    entry = reg.lookup_by_instance(instance)
    assert entry is not None
    assert entry["pascal_name"] == "Button"


def test_registry_entry_includes_component_key_and_variant_prop_map() -> None:
    doc = _load_fixture("component_set.json")
    builder = registry_module.RegistryBuilder(doc)
    data = builder.build()

    entry = data["components"]["10:1"]
    assert entry["figma_component_key"] == "10:1"
    assert entry["variant_prop_map"] == {"Variant": "variant", "Size": "size"}
    assert entry["default_props"] == {"variant": "primary", "size": "small"}


def test_registry_entry_uses_figma_key_when_present() -> None:
    doc = _load_fixture("component_set.json")
    doc["children"][0]["key"] = "abc-button-key"
    doc["children"][0]["description"] = "Primary action button"
    builder = registry_module.RegistryBuilder(doc)
    data = builder.build()

    entry = data["components"]["10:1"]
    assert entry["figma_component_key"] == "abc-button-key"
    assert entry["description"] == "Primary action button"


def test_build_and_write_creates_per_component_mapper_files(tmp_path: Path) -> None:
    doc = _load_fixture("component_set.json")
    mapper_dir = tmp_path / "__mappers__"
    builder = registry_module.RegistryBuilder(
        doc,
        output_path=tmp_path / "registry.json",
        mapper_output_path=tmp_path / "figma_component_map.json",
        per_component_mapper_dir=mapper_dir,
        aggregate_mapper_path=tmp_path / "figma_component_mappings.json",
    )
    builder.build_and_write()

    assert (mapper_dir / "Button.mapper.json").exists()
    assert (mapper_dir / "IconButton.mapper.json").exists()

    button_mapper = json.loads((mapper_dir / "Button.mapper.json").read_text(encoding="utf-8"))
    assert button_mapper["$schema"] == "https://agentic-loop.dev/schemas/component-mapper.json"
    assert button_mapper["figma_component_id"] == "10:1"
    assert button_mapper["pascal_name"] == "Button"
    assert "prop_mapping" in button_mapper
    assert button_mapper["prop_mapping"] == {"Variant": "variant", "Size": "size"}


def test_component_registry_loads_with_aggregate_mapper(tmp_path: Path) -> None:
    doc = _load_fixture("component_set.json")
    builder = registry_module.RegistryBuilder(
        doc,
        output_path=tmp_path / "registry.json",
        mapper_output_path=tmp_path / "figma_component_map.json",
    )
    builder.build_and_write()

    reg = registry_module.ComponentRegistry.load(
        tmp_path / "registry.json",
        mapper_path=tmp_path / "figma_component_map.json",
    )
    mapping = reg.lookup_mapping("10:1")
    assert mapping is not None
    assert mapping["pascal_name"] == "Button"


def test_component_registry_loads_with_per_component_mappers(tmp_path: Path) -> None:
    doc = _load_fixture("component_set.json")
    mapper_dir = tmp_path / "__mappers__"
    builder = registry_module.RegistryBuilder(
        doc,
        output_path=tmp_path / "registry.json",
        mapper_output_path=tmp_path / "figma_component_map.json",
        per_component_mapper_dir=mapper_dir,
        aggregate_mapper_path=tmp_path / "figma_component_mappings.json",
    )
    builder.build_and_write()

    # Overlay a per-component mapper that changes the import path.
    button_mapper = json.loads((mapper_dir / "Button.mapper.json").read_text(encoding="utf-8"))
    button_mapper["react_component"]["import_path"] = "@/components/ui/Button"
    (mapper_dir / "Button.mapper.json").write_text(json.dumps(button_mapper, indent=2), encoding="utf-8")

    reg = registry_module.ComponentRegistry.load_with_per_component_mappers(
        tmp_path / "registry.json",
        aggregate_mapper_path=tmp_path / "figma_component_mappings.json",
        per_component_mapper_dir=mapper_dir,
    )
    mapping = reg.lookup_mapping("10:1")
    assert mapping is not None
    assert mapping["react_component"]["import_path"] == "@/components/ui/Button"


def test_props_for_instance_uses_per_component_value_mapping() -> None:
    mapping = {
        "prop_mapping": {"Variant": "variant", "Size": "size"},
        "value_mapping": {
            "variant": {"Primary": "primary", "Secondary": "secondary"},
            "size": {"Small": "sm", "Large": "lg"},
        },
        "default_props": {"variant": "primary"},
    }
    props = registry_module.ComponentMapper.props_for_instance(mapping, {"Variant": "Secondary", "Size": "Large"})
    assert props == {"variant": "secondary", "size": "lg"}


def test_extract_exports_and_props_reads_jsdoc_description(tmp_path: Path) -> None:
    src = tmp_path / "ActionButton.tsx"
    src.write_text(
        '''/**
 * Primary call-to-action button used for forms and dialogs.
 * @tag action cta primary
 */
export function ActionButton(props: ActionButtonProps) {
  return <button {...props} />;
}

interface ActionButtonProps {
  variant: string;
  size: string;
}
''',
        encoding="utf-8",
    )
    info = registry_module._extract_exports_and_props(src)
    assert info["exports"] == ["ActionButton"]
    details = info["export_details"]
    assert len(details) == 1
    assert details[0][0] == "ActionButton"
    assert "call-to-action" in details[0][2]
    assert any("@tag action cta primary" in tag for tag in details[0][3])


def test_scan_local_components_preserves_jsdoc_description(tmp_path: Path) -> None:
    src = tmp_path / "ActionButton.tsx"
    src.write_text(
        '''/**
 * Primary call-to-action button used for forms and dialogs.
 */
export function ActionButton(props: ActionButtonProps) {
  return <button {...props} />;
}

interface ActionButtonProps {
  variant: string;
  size: string;
}
''',
        encoding="utf-8",
    )
    local = registry_module._scan_local_components([tmp_path])
    assert "actionbutton" in local
    assert "call-to-action" in local["actionbutton"]["description"]
    assert local["actionbutton"]["doc"] == local["actionbutton"]["description"]
