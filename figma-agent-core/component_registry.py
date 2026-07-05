from __future__ import annotations

import importlib.util
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def _to_pascal(name: str) -> str:
    cleaned = re.sub(r"[^\w\s/]+", " ", name)
    parts = re.split(r"[\s/]+", cleaned)
    return "".join(part.capitalize() for part in parts if part)


def _is_component_set(node: Dict[str, Any]) -> bool:
    return node.get("type") == "COMPONENT_SET"


def _is_component(node: Dict[str, Any]) -> bool:
    return node.get("type") == "COMPONENT"


def _is_instance(node: Dict[str, Any]) -> bool:
    return node.get("type") == "INSTANCE"


def _normalize_component_name(name: str) -> str:
    """Collapse a component name to a fuzzy match key."""
    if not name:
        return ""
    cleaned = re.sub(r"[^\w\s]+", " ", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.lower()


def _normalize_prop_name(name: str) -> str:
    """Convert Figma variant property name to a React prop name (camelCase)."""
    if not name:
        return ""
    cleaned = re.sub(r"[^\w\s]+", " ", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    parts = cleaned.split(" ")
    if not parts:
        return ""
    return parts[0].lower() + "".join(p.capitalize() for p in parts[1:])


def _normalize_prop_value(value: Any) -> str:
    """Normalize Figma variant value to a React prop string value."""
    if value is None:
        return ""
    s = str(value).strip()
    return s.lower().replace(" ", "-")


def _extract_jsdoc_blocks(text: str) -> List[Tuple[int, int, str]]:
    """Return (start, end, content) for each /** ... */ block in source order."""
    return [(m.start(), m.end(), m.group(1)) for m in re.finditer(r"/\*\*(.*?)\*/", text, re.DOTALL)]


def _parse_jsdoc(content: str) -> Tuple[str, List[str]]:
    """Extract plain description and @tags from a JSDoc/TSDoc block."""
    lines = []
    for raw in content.split("\n"):
        line = re.sub(r"^\s*\*\s?", "", raw)
        lines.append(line)
    desc_lines = [line.strip() for line in lines if line.strip() and not line.strip().startswith("@")]
    tags = [line.strip() for line in lines if line.strip().startswith("@")]
    description = " ".join(desc_lines)
    return description, tags


def _find_jsdoc_before(text: str, position: int, jsdocs: List[Tuple[int, int, str]]) -> Tuple[str, List[str]]:
    """Return the JSDoc immediately preceding the given position, if any."""
    best: Optional[Tuple[int, int, str]] = None
    for start, end, content in jsdocs:
        if end < position:
            best = (start, end, content)
        else:
            break
    if not best:
        return "", []
    return _parse_jsdoc(best[2])


def _extract_exports_and_props(file_path: Path) -> Dict[str, Any]:
    """Lightweight scan of a React/TypeScript component file."""
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception:
        return {}

    jsdocs = _extract_jsdoc_blocks(text)

    exports: List[Tuple[str, int]] = []
    for m in re.finditer(
        r"export\s+(?:default\s+)?(?:function|const|class)\s+(\w+)" r"|export\s+default\s+(\w+)\s*;?",
        text,
    ):
        name = m.group(1) or m.group(2)
        description, tags = _find_jsdoc_before(text, m.start(), jsdocs)
        exports.append((name, m.start(), description, tags))

    props: Dict[str, str] = {}
    for m in re.finditer(r"interface\s+(\w+)Props\s*\{([^}]*)\}", text, re.DOTALL):
        body = m.group(2)
        for line in body.split("\n"):
            prop_match = re.match(r"\s*(\w+)\??\s*:\s*([^;]+)", line)
            if prop_match:
                props[prop_match.group(1)] = prop_match.group(2).strip()

    return {
        "exports": list({e[0] for e in exports}),
        "export_details": exports,
        "props": props,
    }


def _scan_local_components(scan_dirs: List[Path]) -> Dict[str, Any]:
    """Map normalized component names to existing local files/exports."""
    local: Dict[str, Any] = {}
    seen_files: Set[Path] = set()
    for directory in scan_dirs:
        if not directory.exists():
            continue
        for ext in ("*.tsx", "*.ts", "*.jsx", "*.js"):
            for file_path in directory.rglob(ext):
                if file_path in seen_files:
                    continue
                seen_files.add(file_path)
                info = _extract_exports_and_props(file_path)
                if not info["exports"]:
                    continue
                for name, _pos, description, tags in info.get("export_details", []):
                    key = _normalize_component_name(name)
                    if not key:
                        continue
                    if key not in local:
                        local[key] = {
                            "file_path": str(file_path),
                            "export_name": name,
                            "props": info["props"],
                            "description": description,
                            "doc": description,
                            "tags": tags,
                            "matches": [],
                        }
    return local


class ComponentRegistryError(Exception):
    pass


class ComponentMapper:
    """Builds a Figma component key → React component + props mapper file."""

    def __init__(
        self,
        registry: Dict[str, Any],
        output_path: Optional[Path | str] = None,
        per_component_mapper_dir: Optional[Path | str] = None,
        aggregate_path: Optional[Path | str] = None,
        override_path: Optional[Path | str] = None,
    ):
        self.registry = registry
        self.output_path = output_path or Path("figma_component_map.json")
        self.per_component_mapper_dir = per_component_mapper_dir
        self.aggregate_path = aggregate_path or Path("figma_component_mappings.json")
        self.override_path = override_path

    def build(self) -> Dict[str, Any]:
        components = self.registry.get("components", {})
        local_components = self.registry.get("local_components", {})
        decisions = self.registry.get("component_decisions", {})

        mappings: Dict[str, Any] = {}
        for eid, entry in components.items():
            decision = decisions.get(eid, {})
            action = decision.get("action", "generate")
            local_match = decision.get("local_match")

            prop_mapping, value_mapping, default_props = self._build_prop_mapping(entry)

            if action == "reuse" and local_match:
                file_path = local_match.get("file_path", "")
                export_name = local_match.get("export_name", entry.get("pascal_name", "Component"))
                import_path = self._local_import_path(file_path)
            else:
                file_path = entry.get("file_path", f"src/components/ui/{entry.get('pascal_name', 'Component')}.tsx")
                export_name = entry.get("pascal_name", "Component")
                import_path = f"./{export_name}"

            description = entry.get("description", "")
            doc_url = file_path if action == "generate" else self._local_import_path(file_path)
            mapping: Dict[str, Any] = {
                "figma_component_key": entry.get("figma_component_key", eid),
                "figma_component_id": eid,
                "figma_name": entry.get("name", ""),
                "figma_type": entry.get("node_type", ""),
                "pascal_name": entry.get("pascal_name", export_name),
                "action": action,
                "description": description,
                "doc_url": doc_url,
                "react_component": {
                    "import_path": import_path,
                    "export_name": export_name,
                    "file_path": file_path,
                },
                "prop_mapping": prop_mapping,
                "variant_prop_map": prop_mapping,
                "value_mapping": value_mapping,
                "default_props": default_props,
            }
            if eid in decisions:
                decision = decisions[eid]
                score = decision.get("semantic_score")
                reason = decision.get("semantic_reason")
                if score:
                    mapping["semantic_score"] = score
                if reason:
                    mapping["semantic_reason"] = reason
            mappings[eid] = mapping

        return {
            "version": "1.0",
            "mappings": mappings,
        }

    def build_and_write(self) -> Path:
        mapper = self.build()

        # Apply manual overrides to aggregate mapper output.
        if self.override_path and Path(self.override_path).exists():
            try:
                from mapper_override import load_override_set, merge_overrides_into_mapper
            except ImportError:
                import importlib.util
                override_module_path = Path(__file__).with_name("mapper_override.py")
                spec = importlib.util.spec_from_file_location("mapper_override", str(override_module_path))
                override_module = importlib.util.module_from_spec(spec)
                sys.modules["mapper_override"] = override_module
                spec.loader.exec_module(override_module)
                load_override_set = override_module.load_override_set
                merge_overrides_into_mapper = override_module.merge_overrides_into_mapper
            override_set = load_override_set(self.override_path)
            mapper = merge_overrides_into_mapper(mapper, override_set, self.registry)

        path = Path(self.output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(mapper, indent=2, ensure_ascii=False), encoding="utf-8")

        if self.aggregate_path:
            aggregate_path = Path(self.aggregate_path)
            aggregate_path.parent.mkdir(parents=True, exist_ok=True)
            aggregate_path.write_text(json.dumps(mapper, indent=2, ensure_ascii=False), encoding="utf-8")

        if self.per_component_mapper_dir:
            mapper_dir = Path(self.per_component_mapper_dir)
            mapper_dir.mkdir(parents=True, exist_ok=True)
            for eid, mapping in mapper.get("mappings", {}).items():
                pascal = mapping.get("pascal_name", "Component")
                file_path = mapper_dir / f"{pascal}.mapper.json"
                per_component = dict(mapping)
                per_component["$schema"] = "https://agentic-loop.dev/schemas/component-mapper.json"
                # Do not emit manual_override metadata into per-component files; overrides live centrally.
                per_component.pop("manual_override", None)
                file_path.write_text(json.dumps(per_component, indent=2, ensure_ascii=False), encoding="utf-8")

        return path

    @staticmethod
    def load_per_component_mappers(mapper_dir: Path | str) -> Dict[str, Dict[str, Any]]:
        """Read every `*.mapper.json` in `mapper_dir` and index by `figma_component_id`."""
        directory = Path(mapper_dir)
        if not directory.exists():
            return {}
        result: Dict[str, Dict[str, Any]] = {}
        for file_path in directory.glob("*.mapper.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            eid = data.get("figma_component_id") or data.get("figma_component_key")
            if eid:
                result[eid] = data
        return result

    @staticmethod
    def merge_per_component_mappers(
        aggregate_mapper: Dict[str, Any],
        per_component_mappers: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Return a new aggregate mapper where per-component files override aggregate entries."""
        merged: Dict[str, Any] = {
            "version": aggregate_mapper.get("version", "1.0"),
            "mappings": dict(aggregate_mapper.get("mappings", {})),
        }
        for eid, mapping in per_component_mappers.items():
            merged["mappings"][eid] = mapping
        return merged

    def _build_prop_mapping(self, entry: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, Dict[str, str]], Dict[str, str]]:
        prop_mapping: Dict[str, str] = {}
        value_mapping: Dict[str, Dict[str, str]] = {}
        default_props: Dict[str, str] = {}

        schema = entry.get("variant_properties", {})
        variants = entry.get("variants", [])

        has_variant_props = any(variant.get("variant_properties") for variant in variants)

        if schema:
            for figma_prop, info in schema.items():
                react_prop = _normalize_prop_name(figma_prop)
                prop_mapping[figma_prop] = react_prop
                values = info.get("values", [])
                value_mapping[react_prop] = {v: _normalize_prop_value(v) for v in values}
                default_value = info.get("default")
                if default_value is not None:
                    default_props[react_prop] = _normalize_prop_value(default_value)
        elif has_variant_props:
            # COMPONENT_SET with child components carrying variantProperties.
            for variant in variants:
                for figma_prop, value in variant.get("variant_properties", {}).items():
                    react_prop = _normalize_prop_name(figma_prop)
                    if figma_prop not in prop_mapping:
                        prop_mapping[figma_prop] = react_prop
                        value_mapping[react_prop] = {}
                    value_mapping[react_prop][str(value)] = _normalize_prop_value(value)
        elif variants:
            # Variants encoded in slash-separated names, e.g. "Primary / Large / Filled".
            first_name = variants[0].get("name", "")
            prop_count = first_name.count("/") + 1
            prop_names = [f"prop{i + 1}" for i in range(prop_count)] if prop_count > 1 else ["variant"]
            all_values: Dict[int, Set[str]] = {i: set() for i in range(len(prop_names))}
            for variant in variants:
                parts = [p.strip() for p in variant.get("name", "").split("/")]
                for idx, value in enumerate(parts[: len(prop_names)]):
                    all_values[idx].add(value)
            for idx, prop_name in enumerate(prop_names):
                react_prop = _normalize_prop_name(prop_name)
                prop_mapping[prop_name] = react_prop
                value_mapping[react_prop] = {v: _normalize_prop_value(v) for v in sorted(all_values[idx])}

        return prop_mapping, value_mapping, default_props

    @staticmethod
    def _local_import_path(file_path: str) -> str:
        """Convert an absolute file path to a project import path."""
        path = Path(file_path).as_posix()
        for prefix in ("src/", "app/"):
            if prefix in path:
                idx = path.index(prefix)
                base = path[idx + len(prefix) :]
                no_ext = base.replace(".tsx", "").replace(".ts", "").replace(".jsx", "").replace(".js", "")
                return "@/" + no_ext
        no_ext = Path(path).stem
        return f"./{no_ext}"

    @staticmethod
    def props_for_instance(mapping: Dict[str, Any], variant_props: Dict[str, Any]) -> Dict[str, str]:
        """Translate Figma instance variant properties to React props."""
        prop_mapping = mapping.get("prop_mapping") or mapping.get("variant_prop_map", {})
        value_mapping = mapping.get("value_mapping", {})
        default_props = mapping.get("default_props", {})
        result: Dict[str, str] = {}
        for figma_prop, figma_value in variant_props.items():
            react_prop = prop_mapping.get(figma_prop)
            if not react_prop:
                react_prop = _normalize_prop_name(figma_prop)
            mapped_value = value_mapping.get(react_prop, {}).get(str(figma_value))
            if mapped_value is None:
                mapped_value = _normalize_prop_value(figma_value)
            result[react_prop] = mapped_value
        for react_prop, default_value in default_props.items():
            if react_prop not in result:
                result[react_prop] = default_value
        return result


@dataclass
class RegistryEntry:
    id: str
    figma_component_key: str = ""
    name: str = ""
    description: str = ""
    node_type: str = ""
    pascal_name: str = ""
    file_path: str = ""
    variants: List[Dict[str, Any]] = field(default_factory=list)
    variant_properties: Dict[str, Any] = field(default_factory=dict)
    variant_prop_map: Dict[str, str] = field(default_factory=dict)
    default_props: Dict[str, str] = field(default_factory=dict)
    default_variant_id: Optional[str] = None
    instances: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    is_library: bool = False


@dataclass
class InstanceEntry:
    id: str
    name: str
    component_id: Optional[str]
    component_set_id: Optional[str]
    variant_properties: Dict[str, str] = field(default_factory=dict)
    overrides: List[Dict[str, Any]] = field(default_factory=list)


class RegistryBuilder:
    def __init__(
        self,
        document: Dict[str, Any],
        output_path: Optional[Path | str] = None,
        scan_dirs: Optional[List[Path | str]] = None,
        mapper_output_path: Optional[Path | str] = None,
        per_component_mapper_dir: Optional[Path | str] = None,
        aggregate_mapper_path: Optional[Path | str] = None,
        override_path: Optional[Path | str] = None,
    ):
        self.document = document
        self.output_path = output_path or Path("component_registry.json")
        self.mapper_output_path = mapper_output_path or Path("figma_component_map.json")
        self.per_component_mapper_dir = per_component_mapper_dir
        self.aggregate_mapper_path = aggregate_mapper_path or Path("figma_component_mappings.json")
        self.override_path = override_path
        self.scan_dirs: List[Path] = [Path(d) for d in (scan_dirs or [])]
        self._sets: Dict[str, Dict[str, Any]] = {}
        self._components: Dict[str, Dict[str, Any]] = {}
        self._instances: Dict[str, Dict[str, Any]] = {}
        self._entries: Dict[str, RegistryEntry] = {}
        self._parent_map: Dict[str, Optional[str]] = {}
        self._local_components: Dict[str, Any] = {}
        self._component_decisions: Dict[str, Dict[str, Any]] = {}
        self.semantic_matcher: Optional[Dict[str, Any]] = None

    def build(self, semantic_matcher: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._collect(self.document)
        self._build_entries()
        self._build_dependencies()
        self._map_local_components(semantic_matcher=semantic_matcher)
        graph = self._build_dependency_graph()
        order = self._topological_sort(graph)
        registry = {
            "version": "1.0",
            "components": {e.id: self._entry_to_dict(e) for e in self._entries.values()},
            "instances": {iid: self._instance_to_dict(node) for iid, node in self._instances.items()},
            "dependency_graph": graph,
            "dependency_order": order,
        }
        if self._component_decisions:
            registry["component_decisions"] = self._component_decisions
        if self._local_components:
            registry["local_components"] = self._local_components
        return registry

    def build_mapper(self, semantic_matcher: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        mapper = ComponentMapper(
            self.build(semantic_matcher=semantic_matcher),
            self.mapper_output_path,
            self.per_component_mapper_dir,
            self.aggregate_mapper_path,
            self.override_path,
        ).build()
        if self.override_path and Path(self.override_path).exists():
            try:
                from mapper_override import load_override_set, merge_overrides_into_mapper
            except ImportError:
                import importlib.util
                override_module_path = Path(__file__).with_name("mapper_override.py")
                spec = importlib.util.spec_from_file_location("mapper_override", str(override_module_path))
                override_module = importlib.util.module_from_spec(spec)
                sys.modules["mapper_override"] = override_module
                spec.loader.exec_module(override_module)
                load_override_set = override_module.load_override_set
                merge_overrides_into_mapper = override_module.merge_overrides_into_mapper
            override_set = load_override_set(self.override_path)
            mapper = merge_overrides_into_mapper(mapper, override_set, self.build(semantic_matcher=semantic_matcher))
        return mapper

    def build_and_write(self, semantic_matcher: Optional[Dict[str, Any]] = None) -> Path:
        registry = self.build(semantic_matcher=semantic_matcher)
        path = Path(self.output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
        ComponentMapper(
            registry,
            self.mapper_output_path,
            self.per_component_mapper_dir,
            self.aggregate_mapper_path,
            self.override_path,
        ).build_and_write()
        return path

    def _collect(self, node: Dict[str, Any], parent_id: Optional[str] = None) -> None:
        nid = node.get("id")
        if nid is None:
            return
        self._parent_map[nid] = parent_id

        if _is_component_set(node):
            self._sets[nid] = node
        elif _is_component(node):
            self._components[nid] = node
        elif _is_instance(node):
            self._instances[nid] = node

        for child in node.get("children", []):
            self._collect(child, nid)

    def _build_entries(self) -> None:
        for cid, node in self._sets.items():
            pascal = _to_pascal(node.get("name", "Component"))
            entry = RegistryEntry(
                id=cid,
                figma_component_key=node.get("key") or cid,
                name=node.get("name", ""),
                description=node.get("description", ""),
                node_type="COMPONENT_SET",
                pascal_name=pascal,
                file_path=f"src/components/ui/{pascal}.tsx",
                is_library=node.get("is_external", False),
            )
            self._extract_variant_metadata(entry, node)
            self._entries[cid] = entry

        for cid, node in self._components.items():
            if node.get("componentSetId") in self._entries:
                continue
            pascal = _to_pascal(node.get("name", "Component"))
            entry = RegistryEntry(
                id=cid,
                figma_component_key=node.get("key") or cid,
                name=node.get("name", ""),
                description=node.get("description", ""),
                node_type="COMPONENT",
                pascal_name=pascal,
                file_path=f"src/components/ui/{pascal}.tsx",
                variants=[{"id": cid, "name": node.get("name", ""), "variant_properties": {}}],
                default_variant_id=cid,
                is_library=node.get("is_external", False),
            )
            self._entries[cid] = entry

        for iid, node in self._instances.items():
            ref_set = node.get("componentSetId")
            ref_comp = node.get("componentId")
            if ref_set and ref_set in self._entries:
                self._entries[ref_set].instances.append(iid)
            elif ref_comp and ref_comp in self._entries:
                self._entries[ref_comp].instances.append(iid)

    def _extract_variant_metadata(self, entry: RegistryEntry, node: Dict[str, Any]) -> None:
        children = [c for c in node.get("children", []) if _is_component(c)]
        variants = []
        for child in children:
            vp = child.get("variantProperties") or {}
            variants.append({"id": child.get("id"), "name": child.get("name", ""), "variant_properties": vp})
        entry.variants = variants

        group_props = node.get("variantGroupProperties") or node.get("variantProperties") or {}
        schema: Dict[str, Any] = {}
        if group_props and isinstance(group_props, dict):
            for prop_name, prop_info in group_props.items():
                if isinstance(prop_info, dict):
                    schema[prop_name] = {
                        "type": "enum",
                        "values": prop_info.get("values", []),
                        "default": prop_info.get("defaultValue"),
                    }
                elif isinstance(prop_info, list):
                    schema[prop_name] = {"type": "enum", "values": list(prop_info), "default": prop_info[0] if prop_info else None}
                else:
                    schema[prop_name] = {"type": "enum", "values": [str(prop_info)], "default": str(prop_info)}

        if not schema:
            all_values: Dict[str, Set[str]] = {}
            for variant in variants:
                for key, value in variant["variant_properties"].items():
                    all_values.setdefault(key, set()).add(str(value))
            for key, values in all_values.items():
                sorted_values = sorted(values)
                schema[key] = {"type": "enum", "values": sorted_values, "default": sorted_values[0] if sorted_values else None}

        entry.variant_properties = schema
        entry.variant_prop_map = {
            prop_name: _normalize_prop_name(prop_name) for prop_name in schema
        }
        entry.default_props = {
            _normalize_prop_name(prop_name): _normalize_prop_value(info.get("default"))
            for prop_name, info in schema.items()
            if info.get("default") is not None
        }
        entry.default_variant_id = None
        for variant in variants:
            if all(
                variant["variant_properties"].get(key) == schema.get(key, {}).get("default")
                for key in schema
            ):
                entry.default_variant_id = variant["id"]
                break
        if not entry.default_variant_id and variants:
            entry.default_variant_id = variants[0]["id"]

    def _build_dependencies(self) -> None:
        for iid, node in self._instances.items():
            containing_entry_id = self._find_containing_entry_id(iid)
            if not containing_entry_id:
                continue
            target_id = node.get("componentSetId") or node.get("componentId")
            if target_id and target_id in self._entries and target_id != containing_entry_id:
                self._entries[containing_entry_id].dependencies.append(target_id)

    def _find_containing_entry_id(self, node_id: str) -> Optional[str]:
        while node_id:
            if node_id in self._entries:
                return node_id
            node_id = self._parent_map.get(node_id)
        return None

    def _map_local_components(self, semantic_matcher: Optional[Any] = None) -> None:
        if not self.scan_dirs:
            return
        self._local_components = _scan_local_components(self.scan_dirs)
        semantic_index = None
        if semantic_matcher is not None:
            try:
                from semantic_matcher import SemanticIndex, SemanticMatcher

                semantic_index = SemanticMatcher(
                    SemanticIndex.from_component_registry(
                        {"local_components": self._local_components}
                    ),
                    threshold=semantic_matcher.get("threshold", 0.5),
                )
            except Exception as e:
                print(f"[component_registry] semantic matcher unavailable: {e}")
        for eid, entry in self._entries.items():
            match, semantic_score, semantic_reason = None, 0.0, ""
            if semantic_index is not None:
                entry_dict = self._entry_to_dict(entry)
                match, semantic_score, semantic_reason = semantic_index.find_local_component(entry_dict)
            if not match:
                keys = [
                    _normalize_component_name(entry.pascal_name),
                    _normalize_component_name(entry.name),
                ]
                for key in keys:
                    if key and key in self._local_components:
                        match = self._local_components[key]
                        break
            if match:
                local_props = {p.lower() for p in match.get("props", {}).keys()}
                variant_props = {p.lower() for p in entry.variant_properties.keys()}
                prop_coverage = (
                    len(variant_props & local_props) / len(variant_props) if variant_props else 1.0
                )
                action = "reuse" if prop_coverage >= 0.5 or not variant_props else "generate"
                reason_parts = [f"Local component '{match['export_name']}' matches"]
                if semantic_score:
                    reason_parts.append(f"semantic score {semantic_score:.0%}")
                if semantic_reason and semantic_score:
                    reason_parts.append(f"({semantic_reason})")
                reason_parts.append(f"prop coverage {prop_coverage:.0%}.")
                reason = " ".join(reason_parts)
            else:
                action = "generate"
                reason = "No matching local component found."
            self._component_decisions[eid] = {
                "action": action,
                "reason": reason,
                "local_match": match,
                "semantic_score": semantic_score,
                "semantic_reason": semantic_reason,
            }
            if match:
                match.setdefault("matches", []).append(eid)

    def _build_dependency_graph(self) -> Dict[str, List[str]]:
        graph: Dict[str, List[str]] = {eid: [] for eid in self._entries}
        for eid, entry in self._entries.items():
            for dep in set(entry.dependencies):
                if dep in self._entries:
                    graph[eid].append(dep)
        return graph

    def _topological_sort(self, graph: Dict[str, List[str]]) -> List[str]:
        visited: Set[str] = set()
        temp: Set[str] = set()
        order: List[str] = []
        cycles: List[Tuple[str, str]] = []

        def visit(node: str) -> None:
            if node in visited:
                return
            if node in temp:
                cycles.append((node, node))
                return
            temp.add(node)
            for dep in graph.get(node, []):
                if dep in temp:
                    cycles.append((node, dep))
                    continue
                visit(dep)
            temp.remove(node)
            visited.add(node)
            order.append(node)

        for node in graph:
            visit(node)

        if cycles:
            print(f"[component_registry] dependency cycles detected (broken): {cycles}")

        order.reverse()
        return order

    def _entry_to_dict(self, entry: RegistryEntry) -> Dict[str, Any]:
        data = {
            "id": entry.id,
            "figma_component_key": entry.figma_component_key,
            "name": entry.name,
            "description": entry.description,
            "node_type": entry.node_type,
            "pascal_name": entry.pascal_name,
            "file_path": entry.file_path,
            "variants": entry.variants,
            "variant_properties": entry.variant_properties,
            "variant_prop_map": entry.variant_prop_map,
            "default_props": entry.default_props,
            "default_variant_id": entry.default_variant_id,
            "instances": entry.instances,
            "dependencies": entry.dependencies,
            "is_library": entry.is_library,
        }
        decision = self._component_decisions.get(entry.id)
        if decision:
            data["action"] = decision["action"]
            data["reason"] = decision["reason"]
            if decision.get("local_match"):
                data["local_match"] = decision["local_match"]
        return data

    def _instance_to_dict(self, node: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": node.get("id"),
            "name": node.get("name", ""),
            "component_set_id": node.get("componentSetId"),
            "component_id": node.get("componentId"),
            "variant_properties": node.get("variantProperties") or {},
            "overrides": node.get("overrides") or [],
        }


class ComponentRegistry:
    def __init__(self, data: Dict[str, Any], mapper: Optional[Dict[str, Any]] = None):
        self.data = data
        self.mapper = mapper

    @classmethod
    def load(cls, path: Path | str, mapper_path: Optional[Path | str] = None) -> ComponentRegistry:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        mapper: Optional[Dict[str, Any]] = None
        if mapper_path:
            mapper_file = Path(mapper_path)
            if mapper_file.exists():
                mapper = json.loads(mapper_file.read_text(encoding="utf-8"))
        return cls(data, mapper=mapper)

    @classmethod
    def load_with_per_component_mappers(
        cls,
        registry_path: Path | str,
        aggregate_mapper_path: Optional[Path | str] = None,
        per_component_mapper_dir: Optional[Path | str] = None,
        override_path: Optional[Path | str] = None,
    ) -> ComponentRegistry:
        """Load registry and overlay per-component `*.mapper.json` and manual overrides on the aggregate mapper."""
        registry = cls.load(registry_path)
        aggregate: Optional[Dict[str, Any]] = None
        if aggregate_mapper_path and Path(aggregate_mapper_path).exists():
            aggregate = json.loads(Path(aggregate_mapper_path).read_text(encoding="utf-8"))
        per_component = ComponentMapper.load_per_component_mappers(per_component_mapper_dir or "src/components/ui/__mappers__")
        if aggregate is not None or per_component:
            aggregate = aggregate or {"version": "1.0", "mappings": {}}
            registry.mapper = ComponentMapper.merge_per_component_mappers(aggregate, per_component)
        if override_path and Path(override_path).exists():
            try:
                from mapper_override import load_override_set, merge_overrides_into_mapper
            except ImportError:
                # Allow running when mapper_override is imported via the same directory.
                import importlib.util
                override_module_path = Path(__file__).with_name("mapper_override.py")
                spec = importlib.util.spec_from_file_location("mapper_override", str(override_module_path))
                override_module = importlib.util.module_from_spec(spec)
                sys.modules["mapper_override"] = override_module
                spec.loader.exec_module(override_module)
                load_override_set = override_module.load_override_set
                merge_overrides_into_mapper = override_module.merge_overrides_into_mapper
            override_set = load_override_set(override_path)
            registry.mapper = merge_overrides_into_mapper(registry.mapper or {"version": "1.0", "mappings": {}}, override_set, registry.data)
        return registry

    @property
    def components(self) -> Dict[str, Any]:
        return self.data.get("components", {})

    @property
    def instances(self) -> Dict[str, Any]:
        return self.data.get("instances", {})

    @property
    def dependency_order(self) -> List[str]:
        return self.data.get("dependency_order", [])

    def lookup_by_instance(self, instance: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        set_id = instance.get("componentSetId")
        comp_id = instance.get("componentId")
        if set_id and set_id in self.components:
            return self.components[set_id]
        if comp_id and comp_id in self.components:
            return self.components[comp_id]
        return None

    def lookup(self, component_id: str) -> Optional[Dict[str, Any]]:
        return self.components.get(component_id)

    def get_pascal_name(self, component_id: str) -> Optional[str]:
        entry = self.components.get(component_id)
        return entry.get("pascal_name") if entry else None

    def lookup_mapping(self, component_id: str) -> Optional[Dict[str, Any]]:
        """Return the merged mapper entry for a component, preferring per-component mapper files."""
        if self.mapper:
            return self.mapper.get("mappings", {}).get(component_id)
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Component Registry: Figma document → component_registry.json")
    parser.add_argument("--file", default="figma_node.json", help="Путь к JSON-файлу Figma-структуры.")
    parser.add_argument("--output", default="component_registry.json", help="Путь для сохранения реестра.")
    parser.add_argument("--node-id", default=None, help="ID конкретной ноды (опционально).")
    parser.add_argument(
        "--scan-dir",
        action="append",
        default=[],
        help="Directory to scan for existing local components (repeatable). Defaults to src/components/ui and src/components.",
    )
    parser.add_argument(
        "--mapper-output",
        default="figma_component_map.json",
        help="Путь для сохранения mapper-файла Figma component key → React component + props.",
    )
    parser.add_argument(
        "--per-component-mapper-dir",
        default="src/components/ui/__mappers__",
        help="Директория для записи per-component .mapper.json файлов.",
    )
    parser.add_argument(
        "--aggregate-mapper-path",
        default="figma_component_mappings.json",
        help="Путь для записи aggregate figma_component_mappings.json.",
    )
    parser.add_argument(
        "--semantic-threshold",
        type=float,
        default=0.5,
        help="Minimum semantic similarity score (0-1) for matching Figma components to local components.",
    )
    parser.add_argument(
        "--override-path",
        default=".agent_loop/figma_overrides.json",
        help="Path to manual component mapping override file.",
    )
    args = parser.parse_args()


    doc_path = Path(args.file)
    if not doc_path.exists():
        print(f"[ERROR] File not found: {doc_path}")
        sys.exit(1)
    doc = json.loads(doc_path.read_text(encoding="utf-8"))
    if args.node_id:
        def _find(nid: str, node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            if node.get("id") == nid:
                return node
            for child in node.get("children", []):
                found = _find(nid, child)
                if found:
                    return found
            return None
        target = _find(args.node_id, doc)
        if target:
            doc = target
        else:
            print(f"[WARN] Node {args.node_id} not found, using full document")
    out_path = Path(args.output)
    scan_dirs = args.scan_dir or [Path("src/components/ui"), Path("src/components")]
    builder = RegistryBuilder(
        doc,
        out_path,
        scan_dirs=scan_dirs,
        mapper_output_path=args.mapper_output,
        per_component_mapper_dir=args.per_component_mapper_dir,
        aggregate_mapper_path=args.aggregate_mapper_path,
        override_path=args.override_path,
    )
    semantic_matcher = {"threshold": args.semantic_threshold}
    builder.build_and_write(semantic_matcher=semantic_matcher)
    print(f"[REGISTRY] wrote {out_path}")
    print(f"[MAPPER] wrote {args.mapper_output}")
    if builder.per_component_mapper_dir:
        print(f"[MAPPER] per-component mappers -> {builder.per_component_mapper_dir}")
    print(f"[MAPPER] aggregate -> {builder.aggregate_mapper_path}")
