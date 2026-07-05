import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def _safe_name(name: Any) -> str:
    return re.sub(r"[^\w\-]", "_", str(name or "unnamed")).strip("_") or "unnamed"


def _to_pascal_case(name: str) -> str:
    name = name.strip()
    name = re.sub(r"[^\w\s_]+", " ", name)
    name = re.sub(r"[\s_]+", " ", name).strip()
    words = name.split(" ")
    result = "".join(word[:1].upper() + word[1:] for word in words if word)
    result = re.sub(r"[^A-Za-z0-9]+", "", result)
    if not result or not result[0].isalpha():
        result = "Section" + result
    return result


def _to_camel_case_prop(name: Any) -> str:
    parts = _safe_name(name).split("-")
    return parts[0].lower() + "".join(p.capitalize() for p in parts[1:])


def _class_string(classes: List[str]) -> str:
    if not classes:
        return ""
    return " ".join(classes)


def _render_inline_styles(styles: Dict[str, str]) -> str:
    if not styles:
        return ""
    entries = [
        f'{_to_camel_case(key)}: {json.dumps(value)}'
        for key, value in sorted(styles.items())
    ]
    return f' style={{{{{", ".join(entries)}}}}}'


def _to_camel_case(kebab: str) -> str:
    parts = kebab.split("-")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _safe_prop(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _escape_jsx_text(text: str) -> str:
    import html
    text = html.escape(text, quote=False)
    return text.replace("{", "{'{'").replace("}", "{'}'}")


def _indent(depth: int, spaces: int = 2) -> str:
    return " " * (depth * spaces)


def _collect_all_nodes(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = [node]
    for child in node.get("children", []):
        results.extend(_collect_all_nodes(child))
    return results


def _resolve_component_name(node: Dict[str, Any], mapper: Optional[Dict[str, Any]] = None) -> str:
    """Return the React component name, using mapper export_name if available."""
    name = node.get("component_ref") or node.get("component_name", "Unknown")
    if not mapper:
        return name
    mappings = mapper.get("mappings", {})
    mapping_key = node.get("component_set_id") or node.get("component_id")
    if mapping_key and mapping_key in mappings:
        return mappings[mapping_key].get("react_component", {}).get("export_name", name)
    return name


def _apply_component_mappings(root: Dict[str, Any], mapper: Optional[Dict[str, Any]] = None) -> None:
    """Rewrite component_ref names to mapped export_name in-place."""
    if not mapper:
        return
    for node in _collect_all_nodes(root):
        if node.get("component_ref"):
            node["component_ref"] = _resolve_component_name(node, mapper)


def _detect_component_imports(node: Dict[str, Any], mapper: Optional[Dict[str, Any]] = None) -> List[str]:
    mappings = (mapper or {}).get("mappings", {})
    imports: Set[str] = set()
    for n in _collect_all_nodes(node):
        if not n.get("component_ref"):
            continue
        name = _resolve_component_name(n, mapper)
        import_path = f"@/components/ui/{name}"
        set_id = n.get("component_set_id")
        comp_id = n.get("component_id")
        mapping_key = set_id or comp_id
        if mapping_key and mapping_key in mappings:
            import_path = mappings[mapping_key].get("react_component", {}).get("import_path", import_path)
        imports.add(f'import {name} from "{import_path}"')
    return sorted(imports)


def _render_node(
    node: Dict[str, Any],
    depth: int = 1,
) -> str:
    tag = node.get("tag", "div")
    classes = list(node.get("classes", []))
    variants = node.get("responsive_variants") or {}
    for token in ("sm", "md", "lg", "xl"):
        classes.extend(variants.get(token, []))
    class_attr = f' className="{_class_string(classes)}"' if classes else ""
    style_attr = _render_inline_styles(node.get("inline_styles", {}))

    start_indent = _indent(depth)
    inner_indent = _indent(depth + 1)

    extra_attrs = ""
    data_binding = node.get("data_binding")
    if node.get("src") is not None:
        src = node.get("src")
        alt = node.get("alt", "")
        if isinstance(src, dict) and src.get("prop"):
            extra_attrs += f' src={{props.{src["prop"]}}}'
        else:
            extra_attrs += f' src={_safe_prop(src)}'
        extra_attrs += f' alt={_safe_prop(alt)}'
    elif tag == "img" and data_binding:
        extra_attrs += f' src={{item.{data_binding["field"]}}}'
        if node.get("alt_binding"):
            extra_attrs += f' alt={{item.{node["alt_binding"]["field"]}}}'
        else:
            extra_attrs += f' alt={_safe_prop(node.get("alt", ""))}'

    if node.get("component_ref"):
        name = node["component_ref"]
        props = node.get("variant_props", {})
        props_str = ""
        if props:
            props_str = " " + " ".join(f'{_to_camel_case_prop(k)}={_safe_prop(v)}' for k, v in props.items())
        return f"{start_indent}<{name}{props_str} />"

    if tag == "a" and node.get("href_expr"):
        extra_attrs += f' href={{props.{node["href_expr"]}}}'
    elif tag == "a" and data_binding:
        extra_attrs += f' href={{item.{data_binding["field"]}}}'

    data_model_prop = node.get("data_model_prop")
    children = node.get("children", [])
    rendered_children = "\n".join(_render_node(child, depth + 1) for child in children)

    if data_model_prop:
        body = (
            f"{start_indent}  <{tag}{class_attr}{style_attr}{extra_attrs}>\n"
            f"{rendered_children}\n"
            f"{start_indent}  </{tag}>"
        )
        return (
            f"{start_indent}{{props.{data_model_prop}.map((item) => (\n"
            f"{body}\n"
            f"{start_indent}))}}"
        )

    text_expr = node.get("text_expr")
    text = node.get("text")
    if text_expr:
        inner = f"{{props.{text_expr}}}"
    elif data_binding:
        inner = f"{{item.{data_binding['field']}}}"
    elif text is not None:
        inner = _escape_jsx_text(str(text))
    else:
        inner = ""

    if rendered_children:
        body = rendered_children
        if inner:
            body += f"\n{inner_indent}{inner}"
        return (
            f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}>\n"
            f"{body}\n"
            f"{start_indent}</{tag}>"
        )

    if inner:
        if tag in ("span", "p", "a", "label", "h1", "h2", "h3", "h4", "h5", "h6", "li"):
            return f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}>{inner}</{tag}>"
        return (
            f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}>\n"
            f"{inner_indent}{inner}\n"
            f"{start_indent}</{tag}>"
        )

    if tag == "img":
        return f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs} />"

    return f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs} />"


def _field_type_for_role(role: str) -> str:
    if role == "ctaHref":
        return "string"
    if role == "image":
        return "string"
    if role.endswith("Data"):
        return "any[]"
    return "string"


def _content_field_type(role: str) -> str:
    if role == "ctaHref":
        return "url"
    if role == "image":
        return "image"
    if role.endswith("Data"):
        return "list"
    return "text"


def _split_camel(name: str) -> str:
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    return re.sub(r"\s+", " ", spaced).strip().lower()


def _content_field_label(role: str, prop: str) -> str:
    labels = {
        "heading": "Title",
        "subtitle": "Subtitle",
        "ctaText": "Call to action",
        "ctaHref": "Link URL",
        "image": "Image",
        "text": "Text",
    }
    if role in labels:
        return labels[role]
    if role.endswith("Data"):
        base = prop[:-4] if prop.endswith("Data") else role[:-4]
        human = _split_camel(base)
        return (human[0].upper() + human[1:] + " items") if human else "Items"
    return prop


def _content_field_required(role: str) -> bool:
    return role in ("heading", "ctaText", "ctaHref")


def _section_component_code(name: str, node: Dict[str, Any], imports: List[str], fields: List[Tuple[str, str]]) -> str:
    import_block = "\n".join(imports)
    if import_block:
        import_block += "\n\n"
    body = _render_node(node, depth=2)
    interface_fields = ["  className?: string;"]
    for prop, role in fields:
        interface_fields.append(f"  {prop}?: {_field_type_for_role(role)};")
    return f"""{import_block}export interface {name}Props {{
{chr(10).join(interface_fields)}
}}

export default function {name}(props: {name}Props) {{
  return (
{body}
  );
}}
"""


def _infer_text_role(node: Dict[str, Any]) -> str:
    tag = node.get("tag", "")
    name = (node.get("figma_name") or "").lower()
    if tag in ("h1", "h2") or "heading" in name or "headline" in name or "title" in name:
        return "heading"
    if tag in ("h3", "h4", "h5", "h6") or "subtitle" in name:
        return "subtitle"
    if tag in ("button", "a") or "cta" in name or "button" in name:
        return "ctaText"
    return "text"


def _find_content_slots(node: Dict[str, Any], path: List[int]) -> List[Tuple[List[int], str, str, Any]]:
    slots: List[Tuple[List[int], str, str, Any]] = []
    text = node.get("text")
    if text is not None and isinstance(text, str) and len(text.strip()) > 0:
        slots.append((list(path), "text", _infer_text_role(node), text))
    src = node.get("src")
    if src is not None and isinstance(src, str) and len(src.strip()) > 0:
        slots.append((list(path), "src", "image", src))
    for trigger in node.get("interactive", {}).get("triggers", []):
        ttype = trigger.get("type")
        href = trigger.get("url") or trigger.get("route")
        if href and ttype in ("navigate", "url"):
            slots.append((list(path), "href", "ctaHref", href))
            break
    for idx, child in enumerate(node.get("children", [])):
        slots.extend(_find_content_slots(child, path + [idx]))
    return slots


def _find_data_models(node: Dict[str, Any], path: List[int]) -> List[Tuple[List[int], str, str, Any]]:
    slots: List[Tuple[List[int], str, str, Any]] = []
    dm = node.get("data_model")
    if dm:
        name = dm.get("model", "DataItem")
        var = _to_camel_case_prop(name) + "Data"
        slots.append((list(path), "data_model", var, dm.get("sample_data", [])))
    for idx, child in enumerate(node.get("children", [])):
        slots.extend(_find_data_models(child, path + [idx]))
    return slots


def _assign_prop_names(slots: List[Tuple[List[int], str, str, Any]]) -> List[Tuple[List[int], str, str, str, Any]]:
    seen: Set[str] = set()
    result: List[Tuple[List[int], str, str, str, Any]] = []
    for path, kind, role, value in slots:
        base = role
        prop = base
        counter = 1
        while prop in seen:
            counter += 1
            prop = f"{base}{counter}"
        seen.add(prop)
        result.append((path, kind, role, prop, value))
    return result


def _apply_slot(node: Dict[str, Any], path: List[int], kind: str, prop: str) -> None:
    target = node
    for idx in path[:-1]:
        target = target["children"][idx]
    if kind == "text":
        target["text_expr"] = prop
    elif kind == "src":
        target["src"] = {"prop": prop}
    elif kind == "href":
        target["href_expr"] = prop
    elif kind == "data_model":
        target["data_model_prop"] = prop


@dataclass
class SectionModel:
    name: str
    component_code: str
    data: Dict[str, Any] = field(default_factory=dict)
    fields: List[Tuple[str, str]] = field(default_factory=list)


@dataclass
class ContentModelResult:
    page_code: str
    data_code: str
    data: Dict[str, Any]
    content_model: Dict[str, Any]
    sections: List[SectionModel] = field(default_factory=list)


def _build_page_code(sections: List[SectionModel], data_variable: str = "pageData") -> str:
    imports = [f'import {s.name} from "@/app/sections/{s.name}"' for s in sections]
    imports.insert(0, f'import {{ {data_variable}, sections }} from "./page.data"')
    import_block = "\n".join(imports)
    cases = "\n".join(
        f'        case "{s.name}": return <{s.name} key={{s.slug}} {{...{data_variable}.{s.name}}} />;'
        for s in sections
    )
    rendered = f"""{{sections.map((s) => {{
      switch (s.component) {{
{cases}
        default: return null;
      }}
    }})}}"""
    return f"""{import_block}

export default function Page() {{
  return (
    <div className="relative w-full min-h-screen overflow-x-hidden">
{rendered}
    </div>
  );
}}
"""


def _build_data_code(sections: List[SectionModel], data_variable: str = "pageData") -> str:
    entries: List[str] = []
    for s in sections:
        lines = [f"  {s.name}: {{"]
        for key, value in s.data.items():
            lines.append(f"    {key}: {_safe_prop(value)},")
        lines.append("  },")
        entries.append("\n".join(lines))
    data_body = "\n".join(entries)
    section_entries: List[str] = []
    for s in sections:
        slug = _to_camel_case_prop(s.name)
        section_entries.append(
            f'  {{ name: {_safe_prop(s.name)}, component: {_safe_prop(s.name)}, slug: {_safe_prop(slug)} }},'
        )
    sections_body = "\n".join(section_entries)
    return f"""export const {data_variable} = {{
{data_body}
}};

export const sections = [
{sections_body}
];
"""


def _build_content_model_json(sections: List[SectionModel]) -> Dict[str, Any]:
    section_entries: List[Dict[str, Any]] = []
    for s in sections:
        fields: List[Dict[str, Any]] = []
        for prop, role in s.fields:
            fields.append({
                "name": prop,
                "type": _content_field_type(role),
                "label": _content_field_label(role, prop),
                "required": _content_field_required(role),
                "role": role,
            })
        section_entries.append({
            "name": s.name,
            "slug": _to_camel_case_prop(s.name),
            "component": s.name,
            "fields": fields,
        })
    return {"version": "1", "sections": section_entries}


def build_content_model(
    ast: Dict[str, Any],
    output_dir: str = "src/app/sections",
    page_output: str = "src/app/page.tsx",
    data_output: str = "src/app/page.data.ts",
    content_model_output: str = "content_model.json",
    root_dir: str = ".",
    component_mapper: Optional[Dict[str, Any]] = None,
) -> ContentModelResult:
    abs_root = Path(root_dir).resolve()
    abs_out = Path(output_dir).resolve()
    if not str(abs_out).startswith(str(abs_root)):
        raise ValueError(f"Output directory outside workspace: {output_dir}")
    abs_out.mkdir(parents=True, exist_ok=True)

    root = ast.get("root", ast)
    top_level = root.get("children", [])
    if not top_level:
        top_level = [root]

    sections: List[SectionModel] = []
    for idx, section in enumerate(top_level):
        if section.get("component_context") and not section.get("is_instance"):
            continue
        name = _to_pascal_case(section.get("figma_name") or f"Section{idx + 1}")
        component_node = json.loads(json.dumps(section, ensure_ascii=False))
        _apply_component_mappings(component_node, component_mapper)
        slots = _find_content_slots(component_node, [])
        slots.extend(_find_data_models(component_node, []))
        named = _assign_prop_names(slots)
        data: Dict[str, Any] = {}
        fields: List[Tuple[str, str]] = []
        for path, kind, role, prop, value in named:
            _apply_slot(component_node, path, kind, prop)
            data[prop] = value
            fields.append((prop, role))

        imports = ['import React from "react"']
        imports.extend(_detect_component_imports(component_node, component_mapper))
        code = _section_component_code(name, component_node, imports, fields)
        file_path = abs_out / f"{name}.tsx"
        file_path.write_text(code, encoding="utf-8")
        sections.append(SectionModel(name=name, component_code=code, data=data, fields=fields))

    page_code = _build_page_code(sections)
    data_code = _build_data_code(sections)
    content_model = _build_content_model_json(sections)

    page_path = Path(page_output).resolve()
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(page_code, encoding="utf-8")

    data_path = Path(data_output).resolve()
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(data_code, encoding="utf-8")

    cm_path = Path(content_model_output).resolve()
    cm_path.parent.mkdir(parents=True, exist_ok=True)
    cm_path.write_text(json.dumps(content_model, ensure_ascii=False, indent=2), encoding="utf-8")

    return ContentModelResult(
        page_code=page_code,
        data_code=data_code,
        data={s.name: s.data for s in sections},
        content_model=content_model,
        sections=sections,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Content Model: split Tailwind AST into Page + Sections + Data")
    parser.add_argument("--ast", default="layout_ast.json", help="Path to Tailwind AST JSON")
    parser.add_argument("--output-dir", default="src/app/sections", help="Directory for section components")
    parser.add_argument("--page-output", default="src/app/page.tsx", help="Path for generated page.tsx")
    parser.add_argument("--data-output", default="src/app/page.data.ts", help="Path for generated page.data.ts")
    parser.add_argument("--content-model-output", default="content_model.json", help="Path for generated content_model.json")
    parser.add_argument("--workspace-root", default=".", help="Workspace root for path traversal guard")
    parser.add_argument("--components-mapper", default="figma_component_map.json", help="Path to figma_component_map.json")
    args = parser.parse_args()

    ast_path = Path(args.ast)
    if not ast_path.exists():
        print(f"[ERROR] AST file not found: {ast_path}", file=sys.stderr)
        raise SystemExit(1)

    ast = json.loads(ast_path.read_text(encoding="utf-8"))
    mapper: Optional[Dict[str, Any]] = None
    if args.components_mapper and Path(args.components_mapper).exists():
        mapper = json.loads(Path(args.components_mapper).read_text(encoding="utf-8"))
    result = build_content_model(
        ast,
        output_dir=args.output_dir,
        page_output=args.page_output,
        data_output=args.data_output,
        content_model_output=args.content_model_output,
        root_dir=args.workspace_root,
        component_mapper=mapper,
    )
    print(f"[CONTENT-MODEL] {len(result.sections)} section(s) written to {args.output_dir}")
    for s in result.sections:
        print(f"  - {s.name}")
    print(f"[CONTENT-MODEL] Page -> {args.page_output}")
    print(f"[CONTENT-MODEL] Data -> {args.data_output}")
    print(f"[CONTENT-MODEL] Content Model -> {args.content_model_output}")


if __name__ == "__main__":
    main()
