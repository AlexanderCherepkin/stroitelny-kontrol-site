import html
import json
import re
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_OUTPUT = "src/app/page.tsx"
DEFAULT_ROOT_CLASS = "relative w-full min-h-screen overflow-x-hidden"


def _indent(depth: int, spaces: int = 2) -> str:
    return " " * (depth * spaces)


def _safe_prop(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _style_to_string(styles: Dict[str, str]) -> str:
    if not styles:
        return ""
    pairs = []
    for key, value in sorted(styles.items()):
        kebab = re.sub(r"([A-Z])", r"-\1", key).lower()
        pairs.append(f"{kebab}: {value}")
    return "; ".join(pairs)


def _class_string(classes: List[str]) -> str:
    if not classes:
        return ""
    return " ".join(classes)


def _safe_name(name: Any) -> str:
    return re.sub(r"[^\w\-]", "_", str(name or "unnamed")).strip("_") or "unnamed"


def _form_key(name: Any) -> str:
    return re.sub(r"[^\w]", "_", str(name or "form").lower()).strip("_") or "form"


def _escape_jsx_text(text: str) -> str:
    """Экранирует символы, которые ломают JSX-текст: <, >, &, {, }."""
    text = html.escape(text, quote=False)
    return text.replace("{", "{'{'").replace("}", "{'}'}")


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
    return f' style={{{{{", ".join(entries)}}}}}'


def _sanitize_path(path: str, root_dir: Optional[str] = None) -> Path:
    target = Path(path).resolve()
    root = Path(root_dir).resolve() if root_dir else Path.cwd().resolve()
    if not str(target).startswith(str(root)):
        raise ValueError(f"Path traversal detected: {path}")
    return target


def _node_text(node: Dict[str, Any]) -> str:
    """Возвращает полный текст ноды (plain или rich) для title inference."""
    if node.get("text") is not None:
        return str(node["text"])
    if node.get("rich_text"):
        return "".join(seg.get("text", "") for seg in node["rich_text"])
    return ""


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


def _extract_text_nodes(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    if node.get("text") is not None or node.get("rich_text"):
        return [node]
    results: List[Dict[str, Any]] = []
    for child in node.get("children", []):
        results.extend(_extract_text_nodes(child))
    return results


def _collect_all_nodes(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = [node]
    for child in node.get("children", []):
        results.extend(_collect_all_nodes(child))
    return results


GOOGLE_FONT_FAMILIES = {
    "Inter", "Roboto", "Poppins", "Manrope", "Open Sans", "Lato", "Montserrat",
    "Raleway", "Nunito", "Playfair Display", "Merriweather", "Space Grotesk",
    "DM Sans", "Outfit", "Work Sans", "Fira Sans", "Source Sans 3", "IBM Plex Sans", "PT Sans",
}


def _font_variable_name(family: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", family).lower() or "font"


def _detect_font_imports(ast: Dict[str, Any]) -> List[str]:
    """Возвращает строки импортов и объявлений next/font/google переменных."""
    fonts: set = set()
    root = ast.get("root", ast)
    for node in _collect_all_nodes(root):
        for cls in node.get("classes", []):
            match = re.match(r"font-\[([^\]]+)\]", cls)
            if match:
                family = match.group(1).replace("_", " ")
                if family in GOOGLE_FONT_FAMILIES:
                    fonts.add(family)
            # Поддержка токенизированных шрифтов, например font-sans.
            if cls == "font-sans" and node.get("inline_styles", {}).get("fontFamily"):
                family = node["inline_styles"]["fontFamily"].strip("'")
                if family in GOOGLE_FONT_FAMILIES:
                    fonts.add(family)

    import_names = sorted(f.replace(" ", "_") for f in fonts)
    import_line = 'import { ' + ', '.join(import_names) + ' } from "next/font/google"'
    declarations: List[str] = []
    for family in sorted(fonts):
        import_name = family.replace(" ", "_")
        var_name = _font_variable_name(family)
        declarations.append(
            f'const {var_name} = {import_name}({{" subsets: ["latin"], variable: "--font-{var_name}" }})'
        )
    return [import_line] + declarations


def _detect_image_imports(ast: Dict[str, Any]) -> List[str]:
    root = ast.get("root", ast)
    for node in _collect_all_nodes(root):
        if node.get("asset_type") == "raster" and node.get("asset_width") and node.get("asset_height"):
            return ['import Image from "next/image"']
    return []


def _detect_backend_imports(ast: Dict[str, Any]) -> List[str]:
    root = ast.get("root", ast)
    imports: set = set()
    for node in _collect_all_nodes(root):
        action = node.get("backend_action")
        model = node.get("backend_model")
        if action and model:
            imports.add(f'import {{ {action} }} from "@/app/actions/{model.lower()}Action"')
    return sorted(imports)


def _detect_component_imports(ast: Dict[str, Any], mapper: Optional[Dict[str, Any]] = None) -> List[str]:
    root = ast.get("root", ast)
    imports: set = set()
    mappings = (mapper or {}).get("mappings", {})
    for node in _collect_all_nodes(root):
        if node.get("component_ref"):
            name = _resolve_component_name(node, mapper)
            import_path = f"@/components/ui/{name}"
            set_id = node.get("component_set_id")
            comp_id = node.get("component_id")
            mapping_key = set_id or comp_id
            if mapping_key and mapping_key in mappings:
                import_path = mappings[mapping_key].get("react_component", {}).get("import_path", import_path)
            imports.add(f'import {name} from "{import_path}"')
        elif node.get("component"):
            name = node.get("component_name", node.get("tag", "Unknown"))
            path = node.get("component_path", f"@/app/components/{name}")
            imports.add(f'import {name} from "{path}"')
    return sorted(imports)


def _find_node_by_figma_id(node: Dict[str, Any], figma_id: str) -> Optional[Dict[str, Any]]:
    if node.get("figma_id") == figma_id:
        return node
    for child in node.get("children", []):
        found = _find_node_by_figma_id(child, figma_id)
        if found:
            return found
    return None


def _state_setter(state_key: str) -> str:
    if not state_key:
        return "setState"
    return f"set{state_key[0].upper()}{state_key[1:]}"


def _build_handler(trigger: Dict[str, Any], state_key: str) -> str:
    ttype = trigger.get("type")
    if ttype == "navigate":
        route = trigger.get("route", "/")
        return f"() => router.push({_safe_prop(route)})"
    if ttype == "url":
        url = trigger.get("url", "")
        if trigger.get("external"):
            return f"() => window.open({_safe_prop(url)}, '_blank')"
        return f"() => router.push({_safe_prop(url)})"
    if ttype == "overlay":
        setter = _state_setter(state_key)
        return f"() => {setter}(true)"
    if ttype == "variant":
        setter = _state_setter(state_key)
        return f"() => {setter}(v => !v)"
    return "() => {}"


def _build_state_hooks(nodes: List[Dict[str, Any]]) -> List[str]:
    hooks: List[str] = []
    seen: set = set()
    for node in nodes:
        interactive = node.get("interactive", {})
        state_key = interactive.get("state_key", "")
        if not state_key or state_key in seen:
            continue
        seen.add(state_key)
        setter = _state_setter(state_key)
        hooks.append(f"const [{state_key}, {setter}] = useState(false);")
    return hooks


def _collect_validated_forms(ast: Dict[str, Any]) -> List[Dict[str, Any]]:
    root = ast.get("root", ast)
    forms: List[Dict[str, Any]] = []
    for node in _collect_all_nodes(root):
        action = node.get("backend_action")
        model = node.get("backend_model")
        if not action or not model:
            continue
        has_field = any(n.get("backend_field") for n in _collect_all_nodes(node))
        if has_field:
            key = _safe_name(node.get("figma_name") or "form")
            forms.append({
                "key": key,
                "action": action,
                "model": model,
                "schema_name": f"{model}Schema",
                "type_name": f"{model}Values",
                "node_id": node.get("figma_id"),
            })
    return forms


def _build_form_hooks(forms: List[Dict[str, Any]]) -> List[str]:
    hooks: List[str] = []
    for form in forms:
        key = form["key"]
        hooks.append(f'const [{key}State, {key}Action] = useFormState({form["action"]}, {{ success: false }});')
        hooks.append(
            f'const {{ register: register_{key}, handleSubmit: handleSubmit_{key}, formState: {{ errors: errors_{key} }} }} = '
            f'useForm<{form["type_name"]}>({{ resolver: zodResolver({form["schema_name"]}), mode: "onBlur" }});'
        )
    return hooks


def _build_data_model_consts(ast: Dict[str, Any]) -> List[str]:
    """Generate local data arrays for repeated Figma structures detected by the data model extractor."""
    root = ast.get("root", ast)
    consts: List[str] = []
    seen: set = set()
    for node in _collect_all_nodes(root):
        dm = node.get("data_model")
        if not dm:
            continue
        name = dm.get("model")
        if not name or name in seen:
            continue
        seen.add(name)
        var = _to_camel_case_prop(name) + "Data"
        sample_data = dm.get("sample_data") or []
        consts.append(f"const {var} = {json.dumps(sample_data, ensure_ascii=False)};")
    return consts


def _detect_form_imports(forms: List[Dict[str, Any]]) -> List[str]:
    if not forms:
        return []
    imports = ['"use client"']
    imports.append('import { useForm } from "react-hook-form"')
    imports.append('import { zodResolver } from "@hookform/resolvers/zod"')
    imports.append('import { useFormState } from "react-dom"')
    schemas: set = set()
    for form in forms:
        schemas.add(form["schema_name"])
        schemas.add(form["type_name"])
    imports.append(f'import {{ {", ".join(sorted(schemas))} }} from "@/lib/schemas"')
    return imports


def _detect_interactive_imports(ast: Dict[str, Any]) -> tuple[List[str], bool]:
    root = ast.get("root", ast)
    needs_state = any(n.get("interactive") for n in _collect_all_nodes(root))
    needs_router = False
    for node in _collect_all_nodes(root):
        for trigger in node.get("interactive", {}).get("triggers", []):
            if trigger.get("type") in ("navigate", "url") and not trigger.get("external"):
                needs_router = True
    imports: List[str] = []
    if needs_state:
        imports.append('import { useState } from "react"')
    if needs_router:
        imports.append('import { useRouter } from "next/navigation"')
    return imports, needs_router


def _wrap_conditional(rendered: str, state_key: Optional[str], start_indent: str) -> str:
    if not state_key:
        return rendered
    return f"{start_indent}{{{state_key}}} && (\n{rendered}\n{start_indent})"


def _node_to_tsx(node: Dict[str, Any], depth: int = 1, form_key: Optional[str] = None) -> str:
    tag = node.get("tag", "div")
    classes = list(node.get("classes", []))
    variants = node.get("responsive_variants") or {}
    for token in ("sm", "md", "lg", "xl"):
        classes.extend(variants.get(token, []))
    class_attr = f' className="{_class_string(classes)}"' if classes else ""
    style_attr = _render_inline_styles(node.get("inline_styles", {}))
    figma_id = node.get("figma_id")
    data_attr = f' data-figma-id={_safe_prop(figma_id)}' if figma_id else ""

    text = node.get("text")
    src = node.get("src")
    alt = node.get("alt", "")

    inner_indent = _indent(depth + 1)
    start_indent = _indent(depth)

    extra_attrs = ""
    inline_svg = node.get("inline_svg")
    asset_type = node.get("asset_type")
    asset_width = node.get("asset_width")
    asset_height = node.get("asset_height")
    backend_action = node.get("backend_action")
    backend_field = node.get("backend_field")
    input_type = node.get("input_type", "text")
    required = node.get("required", False)
    interactive = node.get("interactive")
    conditional_state = node.get("conditional_render")
    data_binding = node.get("data_binding")
    data_model = node.get("data_model")

    if backend_action:
        tag = "form"
        form_key = _form_key(node.get("figma_name") or "form")
        extra_attrs += f" action={{{form_key}Action}}"
        extra_attrs += f" onSubmit={{handleSubmit_{form_key}(() => {{}})}}"

    if backend_field:
        input_type = node.get("input_type", "text")
        if input_type == "textarea":
            tag = "textarea"
        elif input_type == "select":
            tag = "select"
        else:
            tag = "input"
        extra_attrs += f" name={_safe_prop(backend_field)}"
        if tag == "input":
            extra_attrs += f" type={_safe_prop(input_type)}"
        if required:
            extra_attrs += " required"
        if text is not None:
            if tag in ("input", "select"):
                extra_attrs += f" placeholder={_safe_prop(text)}"
                text = None
        if form_key:
            extra_attrs += f" {{...register_{form_key}({_safe_prop(backend_field)})}}"

    if tag == "img" and (src or data_binding):
        if data_binding:
            field = data_binding["field"]
            extra_attrs += f' src={{item.{field}}}'
            if alt_binding:
                alt_field = alt_binding["field"]
                extra_attrs += f' alt={{item.{alt_field}}}'
            else:
                extra_attrs += f' alt={_safe_prop(alt)}'
        elif asset_type == "raster" and asset_width and asset_height:
            tag = "Image"
            extra_attrs += (
                f' src={_safe_prop(src)} alt={_safe_prop(alt)}'
                f' width={{{asset_width}}} height={{{asset_height}}}'
            )
        elif inline_svg:
            # inline SVG рендерится напрямую; class/style применяются к обёртке.
            pass
        else:
            extra_attrs += f' src={_safe_prop(src)} alt={_safe_prop(alt)}'

    if interactive:
        state_key = interactive.get("state_key", "")
        for trigger in interactive.get("triggers", []):
            event = trigger.get("event", "on_click")
            handler = _build_handler(trigger, state_key)
            if event == "on_click":
                extra_attrs += f" onClick={{{handler}}}"
            elif event in ("on_hover", "on_mouse_enter"):
                extra_attrs += f" onMouseEnter={{{handler}}}"
            elif event == "on_mouse_leave":
                extra_attrs += f" onMouseLeave={{{handler}}}"

    if tag == "button" and form_key and "submit" not in extra_attrs:
        extra_attrs += ' type="submit"'

    children = node.get("children", [])

    if tag == "input":
        field_error = ""
        if form_key and backend_field:
            field_error = (
                f"\n{start_indent}{{{{errors_{form_key}.{backend_field} && "
                f"<span className=\"text-red-500 text-sm\">{{errors_{form_key}.{backend_field}.message}}</span>}}}}"
            )
        return _wrap_conditional(
            f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}{data_attr} />{field_error}",
            conditional_state,
            start_indent,
        )

    if tag == "textarea":
        field_error = ""
        if form_key and backend_field:
            field_error = (
                f"\n{start_indent}{{{{errors_{form_key}.{backend_field} && "
                f"<span className=\"text-red-500 text-sm\">{{errors_{form_key}.{backend_field}.message}}</span>}}}}"
            )
        inner = _escape_jsx_text(str(text or ""))
        return _wrap_conditional(
            f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}{data_attr}>{inner}</{tag}>{field_error}",
            conditional_state,
            start_indent,
        )

    if tag == "select":
        field_error = ""
        if form_key and backend_field:
            field_error = (
                f"\n{start_indent}{{{{errors_{form_key}.{backend_field} && "
                f"<span className=\"text-red-500 text-sm\">{{errors_{form_key}.{backend_field}.message}}</span>}}}}"
            )
        options = ""
        placeholder_option = ""
        if text is not None:
            placeholder_option = f'<option value="">{_escape_jsx_text(text)}</option>'
        for value in node.get("enum_values", []):
            options += f'<option value={_safe_prop(value)}>{_escape_jsx_text(value)}</option>'
        return _wrap_conditional(
            f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}{data_attr}>{placeholder_option}{options}</{tag}>{field_error}",
            conditional_state,
            start_indent,
        )

    if inline_svg and tag == "img":
        wrapper = f'{start_indent}<div{class_attr}{style_attr}{data_attr}>\n{inner_indent}{inline_svg}\n{start_indent}</div>'
        return _wrap_conditional(wrapper, conditional_state, start_indent)

    if node.get("component_ref"):
        name = node["component_ref"]
        props: Dict[str, Any] = {}
        for k, v in (node.get("variant_props") or {}).items():
            safe_k = _to_camel_case_prop(k)
            props[safe_k] = v
        props_str = ""
        if props:
            props_str = " " + " ".join(f'{k}={_safe_prop(v)}' for k, v in props.items())
        return _wrap_conditional(
            f"{start_indent}<{name}{props_str} />",
            conditional_state,
            start_indent,
        )

    if node.get("component"):
        name = node.get("component_name", tag)
        props = node.get("props", {})
        props_str = ""
        if props:
            props_str = " " + " ".join(f'{k}={_safe_prop(v)}' for k, v in props.items())
        return _wrap_conditional(
            f"{start_indent}<{name}{props_str} />",
            conditional_state,
            start_indent,
        )

    # Inline data-figma-id on component wrappers would be redundant; components own their own DOM.

    rich_text = node.get("rich_text")
    if rich_text:
        rendered_spans: List[str] = []
        for span in rich_text:
            if not span.get("text") and not span.get("newline_before"):
                continue
            span_inner = _indent(depth + 1)
            if span.get("newline_before"):
                rendered_spans.append(f"{span_inner}<br />")
            if span.get("text"):
                span_tag = span.get("tag", "span")
                span_classes = list(span.get("classes", []))
                span_class_attr = f' className="{_class_string(span_classes)}"' if span_classes else ""
                span_extra = ""
                if span_tag == "a":
                    span_extra += f' href={_safe_prop(span.get("href", "#"))}'
                span_text = _escape_jsx_text(span["text"])
                rendered_spans.append(
                    f"{span_inner}<{span_tag}{span_class_attr}{span_extra}>{span_text}</{span_tag}>"
                )
        if rendered_spans:
            body = "\n".join(rendered_spans)
            return _wrap_conditional(
                f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}{data_attr}>\n{body}\n{start_indent}</{tag}>",
                conditional_state,
                start_indent,
            )

    if data_model and children:
        var = _to_camel_case_prop(data_model["model"]) + "Data"
        child_form_key = form_key if form_key else (node.get("backend_action") and _form_key(node.get("figma_name") or "form"))
        rendered_children = "\n".join(_node_to_tsx(child, depth + 1, child_form_key) for child in children)
        body = (
            f"{start_indent}  <{tag}{class_attr}{style_attr}{extra_attrs}{data_attr}>\n"
            f"{rendered_children}\n"
            f"{start_indent}  </{tag}>"
        )
        return (
            f"{start_indent}{{{var}.map((item) => (\n"
            f"{body}\n"
            f"{start_indent}))}}"
        )

    if children:
        child_form_key = form_key if form_key else (node.get("backend_action") and _form_key(node.get("figma_name") or "form"))
        rendered_children = "\n".join(_node_to_tsx(child, depth + 1, child_form_key) for child in children)
        form_status = ""
        if tag == "form" and child_form_key:
            form_status = (
                f"\n{start_indent}{{{child_form_key}State?.success && "
                f"<p className=\"text-green-600 text-sm\">Saved!</p>}}"
                f"\n{start_indent}{{{child_form_key}State?.error && "
                f"<p className=\"text-red-500 text-sm\">{{JSON.stringify({child_form_key}State.error)}}</p>}}"
            )
        return _wrap_conditional(
            (
                f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}{data_attr}>\n"
                f"{rendered_children}\n"
                f"{form_status}{start_indent}</{tag}>"
            ),
            conditional_state,
            start_indent,
        )

    if data_binding:
        field = data_binding["field"]
        inner = f"{{item.{field}}}"
        if tag in ("span", "p", "a", "label", "h1", "h2", "h3", "h4", "h5", "h6", "li"):
            rendered = f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}{data_attr}>{inner}</{tag}>"
        else:
            rendered = (
                f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}{data_attr}>\n"
                f"{inner_indent}{inner}\n"
                f"{start_indent}</{tag}>"
            )
        return _wrap_conditional(rendered, conditional_state, start_indent)

    if text is not None:
        escaped_text = _escape_jsx_text(str(text))
        if tag in ("span", "p", "a", "label"):
            rendered = f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}{data_attr}>{escaped_text}</{tag}>"
        else:
            rendered = f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}{data_attr}>\n{inner_indent}{escaped_text}\n{start_indent}</{tag}>"
        return _wrap_conditional(rendered, conditional_state, start_indent)

    if tag == "img":
        return _wrap_conditional(
            f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}{data_attr} />",
            conditional_state,
            start_indent,
        )

    return _wrap_conditional(
        f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}{data_attr} />",
        conditional_state,
        start_indent,
    )


def _wrap_page(
    title: str,
    imports: List[str],
    sections: List[str],
    state_hooks: Optional[List[str]] = None,
    form_hooks: Optional[List[str]] = None,
    needs_router: bool = False,
    is_client: bool = False,
) -> str:
    import_block = "\n".join(imports)
    sections_block = "\n".join(sections)

    hooks_lines: List[str] = []
    if needs_router:
        hooks_lines.append("const router = useRouter();")
    if state_hooks:
        hooks_lines.extend(state_hooks)
    if form_hooks:
        hooks_lines.extend(form_hooks)

    hooks_block = ""
    if hooks_lines:
        hooks_block = "\n  " + "\n  ".join(hooks_lines) + "\n"

    if is_client:
        return f'''"use client"

{import_block}

export default function Page() {{{hooks_block}
  return (
    <div className="{DEFAULT_ROOT_CLASS}">
{sections_block}
    </div>
  );
}}
'''

    return f'''{import_block}

export const metadata = {{
  title: {json.dumps(title)},
}};

export default function Page() {{{hooks_block}
  return (
    <div className="{DEFAULT_ROOT_CLASS}">
{sections_block}
    </div>
  );
}}
'''


def _collect_fonts(ast: Dict[str, Any]) -> List[str]:
    """Возвращает список Google Font family names, используемых в AST."""
    families: set = set()
    root = ast.get("root", ast)
    for node in _collect_all_nodes(root):
        for cls in node.get("classes", []):
            match = re.match(r"font-\[([^\]]+)\]", cls)
            if match:
                family = match.group(1).replace("_", " ")
                if family in GOOGLE_FONT_FAMILIES:
                    families.add(family)
        if "font-sans" in node.get("classes", []) and node.get("inline_styles", {}).get("fontFamily"):
            family = node["inline_styles"]["fontFamily"].strip("'")
            if family in GOOGLE_FONT_FAMILIES:
                families.add(family)
    return sorted(families)


def _infer_page_title(ast: Dict[str, Any]) -> str:
    root = ast.get("root", ast)
    nodes = _collect_all_nodes(root)
    for node in nodes:
        text = _node_text(node)
        if node.get("tag") in ("h1", "h2") and text:
            return text.strip()
    for node in nodes:
        text = _node_text(node)
        if text:
            return text.strip()
    return "Landing"


def compose_page(ast: Dict[str, Any], title: Optional[str] = None, component_mapper: Optional[Dict[str, Any]] = None) -> str:
    """Превращает Tailwind AST в Next.js page.tsx."""
    page_title = title or _infer_page_title(ast)
    imports = _detect_image_imports(ast)
    imports.extend(_detect_backend_imports(ast))
    imports.extend(_detect_font_imports(ast))
    imports.extend(_detect_component_imports(ast, component_mapper))

    root = ast.get("root", ast)
    _apply_component_mappings(root, component_mapper)

    interactive_nodes = [n for n in _collect_all_nodes(root) if n.get("interactive")]
    interactive_imports, needs_router = _detect_interactive_imports(ast)
    imports.extend(interactive_imports)

    forms = _collect_validated_forms(ast)
    imports.extend(_detect_form_imports(forms))

    if not imports:
        imports = ['import React from "react"']

    for node in interactive_nodes:
        for trigger in node["interactive"].get("triggers", []):
            if trigger.get("type") == "overlay":
                dest_id = trigger.get("destination_id")
                if dest_id:
                    dest_node = _find_node_by_figma_id(root, dest_id)
                    if dest_node:
                        dest_node["conditional_render"] = node["interactive"]["state_key"]

    sections: List[str] = []
    top_level = root.get("children", [])
    if not top_level:
        top_level = [root]

    for section in top_level:
        if section.get("component_context") and not section.get("is_instance"):
            continue
        rendered = _node_to_tsx(section, depth=2)
        if rendered.strip():
            sections.append(rendered)

    state_hooks = _build_state_hooks(interactive_nodes)
    state_hooks.extend(_build_data_model_consts(ast))
    form_hooks = _build_form_hooks(forms)
    is_client = bool(interactive_nodes) or bool(forms) or bool(state_hooks)
    return _wrap_page(
        page_title,
        imports,
        sections,
        state_hooks=state_hooks,
        form_hooks=form_hooks,
        needs_router=needs_router,
        is_client=is_client,
    )


def compose_page_from_ast_file(ast_path: str, title: Optional[str] = None) -> str:
    path = Path(ast_path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return compose_page(data, title=title)


def write_page(code: str, output_path: str, root_dir: Optional[str] = None) -> str:
    target = _sanitize_path(output_path, root_dir=root_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(code)
    return str(target)




def compose_layout(title: str, fonts: Optional[List[str]] = None) -> str:
    fonts = fonts or []
    import_block = 'import type { Metadata } from "next";\nimport React from "react";\nimport "./globals.css";'
    font_declarations: List[str] = []
    class_attr = '"antialiased"'
    if fonts:
        import_block += '\nimport { ' + ', '.join(sorted(f.replace(" ", "_") for f in fonts)) + ' } from "next/font/google";'
        for family in sorted(fonts):
            var_name = _font_variable_name(family)
            font_declarations.append(
                f'const {var_name} = {family.replace(" ", "_")}({{ subsets: ["latin"], variable: "--font-{var_name}" }})'
            )
        var_refs = " ".join(f"{_font_variable_name(f)}.variable" for f in sorted(fonts))
        class_attr = f"{{`${{{var_refs}}} antialiased`}}"
    declarations_block = "\n".join(font_declarations)
    return f"""{import_block}
{declarations_block}

export const metadata: Metadata = {{
  title: {json.dumps(title)},
}};

export default function RootLayout({{
  children,
}}: {{
  children: React.ReactNode;
}}) {{
  return (
    <html lang="en">
      <body className={class_attr}>{{children}}</body>
    </html>
  );
}}
"""


def write_layout(title: str, output_path: str, root_dir: Optional[str] = None, fonts: Optional[List[str]] = None) -> str:
    target = _sanitize_path(output_path, root_dir=root_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    code = compose_layout(title, fonts=fonts)
    with open(target, "w", encoding="utf-8") as f:
        f.write(code)
    return str(target)


def main():
    parser = argparse.ArgumentParser(description="Section Composer: Tailwind AST → Next.js page.tsx")
    parser.add_argument(
        "--ast",
        default="layout_ast.json",
        help="Путь к JSON-файлу с Tailwind AST от layout_engine.py.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Путь для сохранения Next.js-страницы (по умолчанию {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--layout-output",
        default="src/app/layout.tsx",
        help="Путь для сохранения Next.js layout.tsx.",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Заголовок страницы (по умолчанию извлекается из первого заголовка AST).",
    )
    parser.add_argument(
        "--components-mapper",
        default="figma_component_map.json",
        help="Путь к figma_component_map.json для импортов компонентов.",
    )
    args = parser.parse_args()

    ast = json.loads(Path(args.ast).read_text(encoding="utf-8"))
    mapper: Optional[Dict[str, Any]] = None
    if args.components_mapper and Path(args.components_mapper).exists():
        mapper = json.loads(Path(args.components_mapper).read_text(encoding="utf-8"))
    code = compose_page(ast, title=args.title, component_mapper=mapper)
    written_path = write_page(code, args.output)
    print(f"[COMPOSE] Page written to {written_path}")

    page_title = args.title or _infer_page_title(ast)
    fonts = _collect_fonts(ast)
    layout_path = write_layout(page_title, args.layout_output, fonts=fonts)
    print(f"[COMPOSE] Layout written to {layout_path}")


if __name__ == "__main__":
    main()
