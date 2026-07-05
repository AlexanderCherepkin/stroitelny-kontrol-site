import importlib.util
import json
import os
import re
import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field


def _import_component_registry() -> Any:
    if "component_registry" in sys.modules:
        return sys.modules["component_registry"]
    if "figma_component_registry" in sys.modules:
        return sys.modules["figma_component_registry"]
    spec = importlib.util.spec_from_file_location(
        "component_registry", str(Path(__file__).with_name("component_registry.py"))
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["component_registry"] = module
    spec.loader.exec_module(module)
    return module


def _import_layout_engine() -> Any:
    if "layout_engine" in sys.modules:
        return sys.modules["layout_engine"]
    if "figma_layout_engine" in sys.modules:
        return sys.modules["figma_layout_engine"]
    spec = importlib.util.spec_from_file_location(
        "layout_engine", str(Path(__file__).with_name("layout_engine.py"))
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["layout_engine"] = module
    spec.loader.exec_module(module)
    return module


DEFAULT_COMPONENT_PATTERNS: List[str] = [
    "button",
    "card",
    "feature",
    "header",
    "footer",
    "nav",
    "hero",
    "pricing",
    "testimonial",
    "logo",
    "badge",
    "chip",
    "input",
    "form",
    "section",
    "cta",
    "faq",
    "stat",
    "step",
    "team",
    "review",
]

DEFAULT_COMPONENT_NAMES: List[str] = [
    "FeatureCard",
    "InfoCard",
    "PricingCard",
    "TestimonialCard",
    "StatCard",
    "StepCard",
    "TeamCard",
    "ReviewCard",
    "BenefitCard",
    "ValueProp",
]


@dataclass
class ExtractedComponent:
    name: str
    node: Dict[str, Any]
    file_path: Path
    imports: List[str] = field(default_factory=list)


def _to_pascal_case(name: str) -> str:
    name = name.strip()
    name = re.sub(r"[^\w\s_]+", " ", name)
    name = re.sub(r"[\s_]+", " ", name).strip()
    words = name.split(" ")
    result = "".join(word[:1].upper() + word[1:] for word in words if word)
    result = re.sub(r"[^A-Za-z0-9]+", "", result)
    if not result or not result[0].isalpha():
        result = "Figma" + result
    return result


def _sanitize_component_name(name: str) -> str:
    name = name.replace(".tsx", "").replace(".jsx", "").strip()
    if not name:
        raise ValueError("Component name cannot be empty.")
    if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", name):
        raise ValueError(
            f"Invalid component name: '{name}'. "
            "Use PascalCase alphanumeric name starting with a letter."
        )
    return name


def _pattern_base_name(node: Dict[str, Any], patterns: List[str]) -> Optional[str]:
    name = (node.get("figma_name") or "").lower()
    for pattern in patterns:
        if pattern.lower() in name:
            return _to_pascal_case(pattern)
    return None


def _validate_target_dir(target_dir: str, root_dir: str = ".") -> Path:
    abs_root = Path(root_dir).resolve()
    abs_target = Path(target_dir).resolve()
    common = os.path.commonpath([str(abs_root), str(abs_target)])
    if Path(common).resolve() != abs_root:
        raise ValueError(
            f"Path traversal detected: target_dir '{target_dir}' resolves outside root '{root_dir}'."
        )
    return abs_target


def _class_string(classes: List[str]) -> str:
    if not classes:
        return ""
    return " ".join(classes)


def _style_to_string(styles: Dict[str, str]) -> str:
    if not styles:
        return ""
    pairs = []
    for key, value in sorted(styles.items()):
        kebab = re.sub(r"([A-Z])", r"-\1", key).lower()
        pairs.append(f"{kebab}: {value}")
    return "; ".join(pairs)


def _safe_name(name: Any) -> str:
    return re.sub(r"[^\w\-]", "_", str(name or "unnamed")).strip("_") or "unnamed"


def _to_camel_case(kebab: str) -> str:
    parts = kebab.split("-")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _to_camel_case_prop(name: Any) -> str:
    parts = _safe_name(name).split("-")
    return parts[0].lower() + "".join(p.capitalize() for p in parts[1:])


def _render_inline_styles(styles: Dict[str, str]) -> str:
    if not styles:
        return ""
    entries = [
        f"{_to_camel_case(key)}: {json.dumps(value)}"
        for key, value in sorted(styles.items())
    ]
    return f' style={{{", ".join(entries)}}}'


def _safe_prop(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _node_to_tsx(node: Dict[str, Any], depth: int = 1) -> str:
    tag = node.get("tag", "div")
    classes = node.get("classes", [])
    class_attr = f' className="{_class_string(classes)}"' if classes else ""
    style_attr = _render_inline_styles(node.get("inline_styles", {}))

    text = node.get("text")
    src = node.get("src")
    alt = node.get("alt", "")

    inner_indent = " " * ((depth + 1) * 2)
    start_indent = " " * (depth * 2)

    extra_attrs = ""
    if tag == "img" and src:
        extra_attrs += f' src={_safe_prop(src)} alt={_safe_prop(alt)}'

    children = node.get("children", [])

    if node.get("component_ref"):
        name = node["component_ref"]
        props: Dict[str, Any] = {}
        for k, v in (node.get("variant_props") or {}).items():
            safe_k = _to_camel_case_prop(k)
            props[safe_k] = v
        props_str = ""
        if props:
            props_str = " " + " ".join(f'{k}={_safe_prop(v)}' for k, v in props.items())
        return f"{start_indent}<{name}{props_str} />"

    if node.get("component"):
        name = node.get("component_name", tag)
        props = node.get("props", {})
        props_str = ""
        if props:
            props_str = " " + " ".join(f'{k}={_safe_prop(v)}' for k, v in props.items())
        return f"{start_indent}<{name}{props_str} />"

    if children:
        rendered_children = "\n".join(_node_to_tsx(child, depth + 1) for child in children)
        return (
            f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}>\n"
            f"{rendered_children}\n"
            f"{start_indent}</{tag}>"
        )

    if text is not None:
        if tag in ("span", "p", "a", "label"):
            return f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}>{text}</{tag}>"
        return f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}>\n{inner_indent}{text}\n{start_indent}</{tag}>"

    if tag == "img":
        return f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs} />"

    return f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs} />"


def _collect_all_nodes(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = [node]
    for child in node.get("children", []):
        results.extend(_collect_all_nodes(child))
    return results


def _detect_font_imports(node: Dict[str, Any]) -> List[str]:
    fonts: Set[str] = set()
    for n in _collect_all_nodes(node):
        for cls in n.get("classes", []):
            match = re.match(r"font-\[([^\]]+)\]", cls)
            if match:
                family = match.group(1).replace("_", " ")
                if family in (
                    "Inter", "Roboto", "Poppins", "Manrope", "Open Sans", "Lato", "Montserrat"
                ):
                    fonts.add(family.replace(" ", "+"))
    imports = []
    for font in sorted(fonts):
        imports.append(f'import {{ {font.replace("+", " ")} }} from "next/font/google"')
    return imports


def _signature(node: Dict[str, Any]) -> Tuple[Any, ...]:
    tag = node.get("tag", "div")
    classes = node.get("classes", [])
    token_classes = sorted([c for c in classes if "[" not in c])
    child_sigs = tuple(_signature(c) for c in node.get("children", []))
    has_text = 1 if node.get("text") is not None else 0
    has_image = 1 if node.get("src") is not None else 0
    return (tag, tuple(token_classes), child_sigs, has_text, has_image)


def _is_named_candidate(node: Dict[str, Any], patterns: List[str]) -> bool:
    name = (node.get("figma_name") or "").lower()
    if not name:
        return False
    for pattern in patterns:
        if pattern.lower() in name:
            return True
    return False


def _is_component_type(node: Dict[str, Any]) -> bool:
    return node.get("figma_type") in ("COMPONENT", "INSTANCE")


def _has_substance(node: Dict[str, Any]) -> bool:
    children = node.get("children", [])
    classes = node.get("classes", [])
    if node.get("src") is not None:
        return True
    if node.get("text") is not None and len(classes) > 1:
        return True
    if len(children) >= 2:
        return True
    if len(children) == 1:
        child = children[0]
        if child.get("children") and len(classes) > 0:
            return True
        if len(classes) > 1:
            return True
    return False


def _collect_substantial_nodes(
    node: Dict[str, Any],
    patterns: List[str],
    depth: int = 0,
    parent_is_candidate: bool = False,
) -> List[Tuple[Dict[str, Any], int]]:
    results: List[Tuple[Dict[str, Any], int]] = []
    if node.get("component_ref"):
        # Real Figma instances are rendered as typed components; do not extract them as local feature components.
        return results
    is_candidate = False
    if depth > 0 and not parent_is_candidate:
        if _is_named_candidate(node, patterns) or _is_component_type(node) or _has_substance(node):
            is_candidate = True
    if is_candidate:
        results.append((node, depth))
        return results
    for child in node.get("children", []):
        results.extend(_collect_substantial_nodes(child, patterns, depth + 1, is_candidate))
    return results


def _name_for_duplicate(sig: Tuple[Any, ...], index: int) -> str:
    name = DEFAULT_COMPONENT_NAMES[index % len(DEFAULT_COMPONENT_NAMES)]
    quotient = index // len(DEFAULT_COMPONENT_NAMES)
    if quotient > 0:
        name = f"{name}{quotient}"
    return name


def _assign_component_names(
    candidates: List[Tuple[Dict[str, Any], int]],
    patterns: List[str],
    min_duplicates: int = 2,
) -> List[Tuple[Dict[str, Any], str]]:
    component_type_nodes: List[Dict[str, Any]] = []
    duplicate_groups: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}

    for node, _ in candidates:
        if _is_component_type(node):
            component_type_nodes.append(node)
        else:
            sig = _signature(node)
            duplicate_groups.setdefault(sig, []).append(node)

    assignments: List[Tuple[Dict[str, Any], str]] = []
    used: Set[str] = set()

    def _claim_name(base: str) -> str:
        safe = _sanitize_component_name(_to_pascal_case(base))
        if safe not in used:
            used.add(safe)
            return safe
        counter = 2
        while True:
            candidate = f"{safe}{counter}"
            if candidate not in used:
                used.add(candidate)
                return candidate
            counter += 1

    duplicate_index = 0
    for sig, group in duplicate_groups.items():
        if len(group) >= min_duplicates:
            # Prefer a pattern-derived name from any group member, else generic.
            base_name: Optional[str] = None
            for node in group:
                base_name = _pattern_base_name(node, patterns)
                if base_name:
                    break
            if not base_name:
                base_name = _name_for_duplicate(sig, duplicate_index)
                duplicate_index += 1
            for idx, node in enumerate(group):
                name = base_name if idx == 0 else f"{base_name}{idx + 1}"
                assignments.append((node, _claim_name(name)))
        else:
            for node in group:
                if _is_named_candidate(node, patterns):
                    base_name = _to_pascal_case(node.get("figma_name") or "Component")
                    assignments.append((node, _claim_name(base_name)))

    for node in component_type_nodes:
        base_name = _to_pascal_case(node.get("figma_name") or "Component")
        assignments.append((node, _claim_name(base_name)))

    return assignments


def _find_node_by_id(root: Dict[str, Any], figma_id: str) -> Optional[Dict[str, Any]]:
    if not isinstance(root, dict):
        return None
    if root.get("figma_id") == figma_id:
        return root
    for child in root.get("children", []):
        found = _find_node_by_id(child, figma_id)
        if found:
            return found
    return None


def _replace_node_in_tree(
    node: Dict[str, Any],
    figma_id: str,
    replacement: Dict[str, Any],
) -> bool:
    for idx, child in enumerate(node.get("children", [])):
        if child.get("figma_id") == figma_id:
            node["children"][idx] = replacement
            return True
        if _replace_node_in_tree(child, figma_id, replacement):
            return True
    return False


def _wrap_component_code(name: str, node: Dict[str, Any], imports: List[str]) -> str:
    import_block = "\n".join(imports)
    if import_block:
        import_block += "\n\n"
    rendered = _node_to_tsx(node, depth=2)
    return f"""{import_block}export default function {name}() {{
  return (
{rendered}
  );
}}
"""


class ComponentExtractor:
    def __init__(
        self,
        output_dir: str = "src/app/components",
        root_dir: str = ".",
        patterns: Optional[List[str]] = None,
        min_duplicates: int = 2,
    ):
        self.output_dir = _validate_target_dir(output_dir, root_dir)
        self.patterns = patterns or DEFAULT_COMPONENT_PATTERNS
        self.min_duplicates = max(min_duplicates, 2)
        self.root_dir = Path(root_dir).resolve()

    def extract(
        self,
        ast: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ExtractedComponent]]:
        root = ast.get("root", ast)
        if not isinstance(root, dict):
            raise ValueError("AST root must be a dict")

        candidates = _collect_substantial_nodes(root, self.patterns)
        assigned = _assign_component_names(candidates, self.patterns, self.min_duplicates)

        extracted_ids: Set[str] = set()
        extracted: List[ExtractedComponent] = []
        page_root = json.loads(json.dumps(root, ensure_ascii=False))

        for node, name in assigned:
            figma_id = node.get("figma_id")
            if not figma_id:
                continue
            if figma_id in extracted_ids:
                continue

            existing = _find_node_by_id(page_root, figma_id)
            if not existing:
                continue

            self.output_dir.mkdir(parents=True, exist_ok=True)
            file_path = self.output_dir / f"{name}.tsx"

            component_node = json.loads(json.dumps(existing, ensure_ascii=False))
            imports = _detect_font_imports(component_node)
            if not imports:
                imports = ['import React from "react"']

            code = _wrap_component_code(name, component_node, imports)
            file_path.write_text(code, encoding="utf-8")

            component_path = "@/app/components/" + name
            replacement = {
                "tag": name,
                "component": True,
                "component_name": name,
                "component_path": component_path,
                "props": {},
                "children": [],
                "figma_id": figma_id,
            }
            _replace_node_in_tree(page_root, figma_id, replacement)

            extracted.append(ExtractedComponent(
                name=name,
                node=component_node,
                file_path=file_path,
                imports=imports,
            ))
            extracted_ids.add(figma_id)

        page_ast = {"root": page_root}
        return page_ast, extracted


class ComponentGenerator:
    def __init__(
        self,
        figma_document: Dict[str, Any],
        output_dir: str = "src/components/ui",
        root_dir: str = ".",
        layout_config: Optional[Dict[str, Any]] = None,
        mapper_file: Optional[str] = None,
    ):
        self.figma_document = figma_document
        self.output_dir = _validate_target_dir(output_dir, root_dir)
        self.layout_config = layout_config or {}
        self.mapper_file = mapper_file
        self._registry_data: Optional[Dict[str, Any]] = None
        self._mapper_data: Optional[Dict[str, Any]] = None
        self._generated: List[ExtractedComponent] = []

    @property
    def registry(self) -> Dict[str, Any]:
        if self._registry_data is None:
            mod = _import_component_registry()
            self._registry_data = mod.RegistryBuilder(self.figma_document).build()
        return self._registry_data

    @property
    def mapper(self) -> Optional[Dict[str, Any]]:
        if self._mapper_data is None and self.mapper_file:
            try:
                self._mapper_data = json.loads(Path(self.mapper_file).read_text(encoding="utf-8"))
            except Exception:
                self._mapper_data = {}
        return self._mapper_data

    def generate(self) -> Tuple[Dict[str, Any], List[ExtractedComponent]]:
        registry_mod = _import_component_registry()
        layout_mod = _import_layout_engine()

        registry = self.registry
        wrapper = registry_mod.ComponentRegistry(registry)
        config = {**self.layout_config, "component_registry": registry, "component_mapper": self.mapper}
        engine = layout_mod.FigmaLayoutEngine(config)

        generated: List[ExtractedComponent] = []
        for entry_id in registry.get("dependency_order", []):
            entry = registry["components"].get(entry_id)
            if not entry or entry.get("is_library"):
                continue
            if entry.get("action") == "reuse":
                continue
            node = self._resolve_component_node(entry)
            if not node:
                continue
            result = engine.convert(node)
            ast = result.root.to_dict()
            code = self._generate_component_source(entry, ast)
            file_path = self.output_dir / f"{entry['pascal_name']}.tsx"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(code, encoding="utf-8")
            generated.append(ExtractedComponent(name=entry["pascal_name"], node=ast, file_path=file_path, imports=[]))

        self._generated = generated
        return registry, generated

    def _find_node_by_id(self, node: Dict[str, Any], target_id: str) -> Optional[Dict[str, Any]]:
        if node.get("id") == target_id:
            return node
        for child in node.get("children", []):
            found = self._find_node_by_id(child, target_id)
            if found:
                return found
        return None

    def _resolve_component_node(self, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if entry["node_type"] == "COMPONENT":
            return self._find_node_by_id(self.figma_document, entry["id"])
        default_id = entry.get("default_variant_id")
        if default_id:
            set_node = self._find_node_by_id(self.figma_document, entry["id"])
            if set_node:
                for child in set_node.get("children", []):
                    if child.get("id") == default_id:
                        return child
        return self._find_node_by_id(self.figma_document, entry["id"])

    def _generate_component_source(self, entry: Dict[str, Any], ast: Dict[str, Any]) -> str:
        name = entry["pascal_name"]
        override_props = self._apply_text_overrides(ast)
        interface_lines = self._build_interface(entry, override_props)
        imports = self._collect_imports(entry)
        body = self._render_component_body(ast)
        import_block = "\n".join(imports)
        return f"""{import_block}
{interface_lines}

export default function {name}(props: {name}Props) {{
  return (
{body}
  );
}}
"""

    def _build_interface(self, entry: Dict[str, Any], override_props: Dict[str, Any]) -> str:
        name = entry["pascal_name"]
        lines: List[str] = []
        for prop_name, info in entry.get("variant_properties", {}).items():
            safe = _to_camel_case_prop(prop_name)
            values = info.get("values", [])
            if values:
                type_str = " | ".join(json.dumps(v) for v in values)
            else:
                type_str = "string"
            default = info.get("default")
            optional = default is not None
            marker = "?" if optional else ""
            lines.append(f"  {safe}{marker}: {type_str};")
        for prop_name in sorted(override_props):
            lines.append(f"  {prop_name}?: string;")
        lines.append("  className?: string;")
        lines.append("  children?: React.ReactNode;")
        if not lines:
            return f"export interface {name}Props {{}}"
        return f"export interface {name}Props {{\n" + "\n".join(lines) + "\n}}"

    def _collect_imports(self, entry: Dict[str, Any]) -> List[str]:
        imports = ['import React from "react"']
        registry = self.registry
        mapper = self.mapper or {}
        mappings = mapper.get("mappings", {})
        for dep_id in entry.get("dependencies", []):
            dep_entry = registry.get("components", {}).get(dep_id)
            if not dep_entry:
                continue
            mapping = mappings.get(dep_id, {})
            react_component = mapping.get("react_component", {})
            export_name = react_component.get("export_name", dep_entry["pascal_name"])
            import_path = react_component.get("import_path", f"./{dep_entry['pascal_name']}")
            imports.append(f'import {{ {export_name} }} from "{import_path}";')
        return imports

    def _apply_text_overrides(self, ast: Dict[str, Any]) -> Dict[str, Any]:
        override_props: Dict[str, Any] = {}
        seen: Set[str] = set()

        def walk(node: Dict[str, Any]) -> None:
            text = node.get("text")
            figma_name = node.get("figma_name")
            if text is not None and figma_name:
                base = _to_camel_case_prop(figma_name)
                if not base or base in ("text", "unnamed"):
                    return
                prop_name = base
                counter = 2
                while prop_name in seen:
                    prop_name = f"{base}{counter}"
                    counter += 1
                seen.add(prop_name)
                override_props[prop_name] = {"type": "string", "default": text}
                node["text"] = f'{{props.{prop_name} ?? {json.dumps(text)}}}'
            for child in node.get("children", []):
                walk(child)

        walk(ast)
        return override_props

    def _render_component_body(self, ast: Dict[str, Any]) -> str:
        tag = ast.get("tag", "div")
        classes = ast.get("classes", [])
        class_expr = self._class_name_expression(classes)
        style_attr = _render_inline_styles(ast.get("inline_styles", {}))
        children = ast.get("children", [])
        rendered_children = "\n".join(_node_to_tsx(child, depth=2) for child in children)
        start_indent = "  "
        if rendered_children:
            return f'{start_indent}<{tag} className={{{class_expr}}}{style_attr}>\n{rendered_children}\n{start_indent}  {{props.children}}\n{start_indent}</{tag}>'
        text = ast.get("text")
        if text is not None:
            return f'{start_indent}<{tag} className={{{class_expr}}}{style_attr}>{text}</{tag}>'
        return f'{start_indent}<{tag} className={{{class_expr}}}{style_attr} />'

    def _class_name_expression(self, classes: List[str]) -> str:
        base = _class_string(classes)
        if base:
            return f'"{base}" + (props.className ? " " + props.className : "")'
        return 'props.className || ""'


def run_extraction(
    ast_path: str,
    output_dir: str = "src/app/components",
    page_ast_output: str = "page_ast.json",
    component_map_output: str = "component_map.json",
    patterns: Optional[List[str]] = None,
    min_duplicates: int = 2,
    root_dir: str = ".",
) -> Dict[str, Any]:
    ast_file = Path(ast_path)
    if not ast_file.exists():
        raise FileNotFoundError(f"AST file not found: {ast_path}")

    with open(ast_file, "r", encoding="utf-8") as f:
        ast = json.load(f)

    extractor = ComponentExtractor(
        output_dir=output_dir,
        root_dir=root_dir,
        patterns=patterns,
        min_duplicates=min_duplicates,
    )
    page_ast, components = extractor.extract(ast)

    page_ast_path = Path(page_ast_output)
    page_ast_path.parent.mkdir(parents=True, exist_ok=True)
    with open(page_ast_path, "w", encoding="utf-8") as f:
        json.dump(page_ast, f, ensure_ascii=False, indent=2)

    root_path = Path(root_dir).resolve()
    component_map = {
        "components": [
            {
                "name": c.name,
                "file": str(c.file_path.relative_to(root_path)),
                "figma_id": c.node.get("figma_id"),
                "figma_name": c.node.get("figma_name"),
                "import_path": "@/app/components/" + c.name,
            }
            for c in components
        ],
        "extracted_count": len(components),
        "page_ast": str(page_ast_path.resolve()),
    }

    map_path = Path(component_map_output)
    map_path.parent.mkdir(parents=True, exist_ok=True)
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(component_map, f, ensure_ascii=False, indent=2)

    return component_map


def main():
    parser = argparse.ArgumentParser(
        description="Component Extractor: Tailwind AST → reusable Next.js components + page AST"
    )
    parser.add_argument(
        "--ast",
        default="layout_ast.json",
        help="Путь к JSON-файлу с Tailwind AST от layout_engine.py.",
    )
    parser.add_argument(
        "--output-dir",
        default="src/app/components",
        help="Директория для сохранения компонентов.",
    )
    parser.add_argument(
        "--page-ast-output",
        default="page_ast.json",
        help="Путь для сохранения урезанного AST страницы.",
    )
    parser.add_argument(
        "--component-map-output",
        default="component_map.json",
        help="Путь для сохранения реестра компонентов.",
    )
    parser.add_argument(
        "--patterns",
        default=None,
        help='JSON-список строк паттернов имён для извлечения, например ["card", "hero"].',
    )
    parser.add_argument(
        "--min-duplicates",
        type=int,
        default=2,
        help="Минимальное число структурных дубликатов для извлечения (по умолчанию 2).",
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Корень рабочего пространства для проверки path traversal.",
    )
    parser.add_argument(
        "--generate-ui",
        action="store_true",
        help="Сгенерировать src/components/ui/*.tsx из реальных Figma Component Sets.",
    )
    parser.add_argument(
        "--figma-file",
        default="figma_node.json",
        help="Путь к JSON-файлу Figma-структуры для --generate-ui.",
    )
    parser.add_argument(
        "--mapper-file",
        default="figma_component_map.json",
        help="Путь к figma_component_map.json для использования существующих компонентов.",
    )
    args = parser.parse_args()

    if args.generate_ui:
        figma_path = Path(args.figma_file)
        if not figma_path.exists():
            print(f"[ERROR] Figma file not found: {figma_path}")
            raise SystemExit(1)
        doc = json.loads(figma_path.read_text(encoding="utf-8"))
        gen = ComponentGenerator(
            doc,
            output_dir=args.output_dir,
            root_dir=args.workspace_root,
            mapper_file=args.mapper_file,
        )
        registry, components = gen.generate()
        print(f"[GENERATE-UI] {len(components)} component(s) written to {args.output_dir}")
        for c in components:
            print(f"  - {c.name} -> {c.file_path}")
        return

    patterns: Optional[List[str]] = None
    if args.patterns:
        try:
            patterns = json.loads(args.patterns)
            if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
                raise ValueError("patterns must be a JSON list of strings")
        except Exception as e:
            print(f"[ERROR] Invalid --patterns value: {e}")
            raise SystemExit(1)

    result = run_extraction(
        ast_path=args.ast,
        output_dir=args.output_dir,
        page_ast_output=args.page_ast_output,
        component_map_output=args.component_map_output,
        patterns=patterns,
        min_duplicates=args.min_duplicates,
        root_dir=args.workspace_root,
    )
    print(f"[EXTRACT] {result['extracted_count']} component(s) written to {args.output_dir}")
    for c in result["components"]:
        print(f"  - {c['name']} -> {c['file']}")


if __name__ == "__main__":
    main()
