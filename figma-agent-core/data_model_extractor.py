import argparse
import json
import re
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
        result = "Model" + result
    return result


def _normalize_name(name: str) -> str:
    """Strip trailing numbers and version suffixes from Figma node names."""
    n = re.sub(r"\s*\d+\s*$", "", name or "").strip()
    n = re.sub(r"\s*/\s*\d+\s*$", "", n).strip()
    return n or "Group"


def _field_name_from_node(node: Dict[str, Any], role_hint: str = "text") -> str:
    name = _safe_name(node.get("name", "")).lower()
    tag = node.get("tag", "")
    if role_hint == "image":
        if name and name not in ("image", "img"):
            return name
        return "imageUrl"
    if tag in ("h1", "h2") or "title" in name or "heading" in name or "headline" in name:
        return "title"
    if tag in ("h3", "h4", "h5", "h6") or "subtitle" in name:
        return "subtitle"
    if tag in ("button", "a") or "cta" in name or "button" in name:
        return "ctaText"
    if "name" in name:
        return "name"
    if "label" in name:
        return "label"
    if "description" in name or "body" in name or "copy" in name:
        return "description"
    if role_hint == "href":
        return "href"
    return role_hint


def _is_visible(node: Dict[str, Any]) -> bool:
    return node.get("visible", True) is True


def _node_type(node: Dict[str, Any]) -> str:
    return str(node.get("type", "UNKNOWN"))


def _has_image_fill(node: Dict[str, Any]) -> bool:
    for f in node.get("fills", []) or []:
        if f.get("type") == "IMAGE":
            return True
    return False


def _is_image_node(node: Dict[str, Any]) -> bool:
    return node.get("type") == "IMAGE" or _has_image_fill(node)


def _is_text_node(node: Dict[str, Any]) -> bool:
    return node.get("type") == "TEXT" or node.get("characters") is not None


def _text_value(node: Dict[str, Any]) -> Optional[str]:
    chars = node.get("characters")
    if isinstance(chars, str):
        return chars.strip() or None
    return None


def _collect_leaf_fields(
    node: Dict[str, Any],
    prefix: str = "",
    max_depth: int = 3,
) -> List[Tuple[str, str, Any, str]]:
    """Collect primitive field candidates from a prototype node.

    Returns tuples of (field_name, field_type, sample_value, role).
    """
    if max_depth <= 0 or not isinstance(node, dict) or not _is_visible(node):
        return []

    fields: List[Tuple[str, str, Any, str]] = []

    if _is_text_node(node):
        text = _text_value(node)
        if text:
            role = _field_name_from_node(node, "text")
            fields.append((_unique_field_name(prefix or role, fields), "String", text, role))
        return fields

    if _is_image_node(node):
        role = "imageUrl"
        fields.append((_unique_field_name(prefix or role, fields), "String", None, role))
        return fields

    triggers = node.get("prototype", {}).get("triggers", []) or []
    for trigger in triggers:
        ttype = trigger.get("type")
        href = None
        if ttype == "URL":
            href = trigger.get("url")
        elif ttype == "NODE":
            href = trigger.get("nodeID") or trigger.get("route")
        if href:
            role = "href"
            fields.append((_unique_field_name(prefix or role, fields), "String", href, role))
            break

    children = [c for c in node.get("children", []) if isinstance(c, dict) and _is_visible(c)]
    for idx, child in enumerate(children):
        # Leaf primitives name themselves by semantic role; grouped children keep their parent prefix.
        if _is_text_node(child) or _is_image_node(child):
            child_prefix = ""
        else:
            child_name = _normalize_name(child.get("name", ""))
            child_prefix = child_name if child_name and child_name.lower() not in ("group", "frame", "auto layout", "vector") else ""
        child_fields = _collect_leaf_fields(child, prefix=child_prefix, max_depth=max_depth - 1)
        for fname, ftype, fvalue, role in child_fields:
            fields.append((_unique_field_name(fname, fields), ftype, fvalue, role))
    return fields


def _unique_field_name(base: str, existing: List[Tuple[str, str, Any, str]]) -> str:
    names = {f[0] for f in existing}
    if base not in names:
        return base
    counter = 2
    while f"{base}{counter}" in names:
        counter += 1
    return f"{base}{counter}"


def _node_fingerprint(node: Dict[str, Any]) -> Tuple[str, ...]:
    """Structural fingerprint based on type, normalized name, and child primitives."""
    if not isinstance(node, dict):
        return ("UNKNOWN",)
    ntype = _node_type(node)
    name = _normalize_name(node.get("name", ""))
    children = [c for c in node.get("children", []) if isinstance(c, dict) and _is_visible(c)]
    child_types = tuple(_node_type(c) for c in children)
    has_text = any(_is_text_node(c) for c in children)
    has_img = any(_is_image_node(c) for c in children)
    child_count = len(children)
    return (ntype, name, child_count, has_text, has_img) + child_types[:6]


def _model_name_from_fingerprint(name: str, fingerprint: Tuple[str, ...]) -> str:
    base = _to_pascal_case(name)
    generic = {"Frame", "Group", "Component", "Instance", "Vector", "Rectangle", "Ellipse", "Page"}
    if base and base not in generic:
        return base
    # Try to infer from child types
    child_types = [p for p in fingerprint[5:] if p]
    if child_types.count("TEXT") >= 2:
        return "ContentItem"
    if "IMAGE" in child_types:
        return "MediaItem"
    return "DataItem"


def _prisma_model_code(name: str, fields: List[Dict[str, Any]]) -> str:
    lines = [f"model {name} {{"]
    lines.append("  id String @id @default(uuid())")
    for f in fields:
        ftype = f.get("type", "String")
        if ftype.endswith("[]"):
            ftype = "Json"
        lines.append(f"  {f['name']} {ftype}")
    lines.append("}")
    return "\n".join(lines)


class DataModelExtractor:
    def __init__(self, min_occurrences: int = 2, top_n: int = 10) -> None:
        self.min_occurrences = min_occurrences
        self.top_n = top_n

    def extract(self, root: Dict[str, Any]) -> Dict[str, Any]:
        candidates: Dict[Tuple[str, ...], List[Tuple[Dict[str, Any], str]]] = {}
        for node in self._walk(root):
            fp = _node_fingerprint(node)
            candidates.setdefault(fp, []).append((node, node.get("id", "")))

        models: List[Dict[str, Any]] = []
        for fp, occurrences in candidates.items():
            if len(occurrences) < self.min_occurrences:
                continue
            prototype, sample_id = occurrences[0]
            raw_name = _normalize_name(prototype.get("name", ""))
            name = _model_name_from_fingerprint(raw_name, fp)
            fields_with_samples = _collect_leaf_fields(prototype)
            field_dicts: List[Dict[str, Any]] = []
            sample: Dict[str, Any] = {}
            field_map: Dict[str, str] = {}
            for fname, ftype, fvalue, role in fields_with_samples:
                field_dicts.append({"name": fname, "type": ftype})
                if fvalue is not None:
                    sample[fname] = fvalue
                field_map[role] = fname
            occurrence_ids = [oid for _, oid in occurrences]
            sample_data: List[Dict[str, Any]] = []
            for occ_node, _ in occurrences:
                occ_fields = _collect_leaf_fields(occ_node)
                row: Dict[str, Any] = {}
                for fname, ftype, fvalue, role in occ_fields:
                    if fvalue is not None:
                        row[fname] = fvalue
                sample_data.append(row)
            confidence = min(1.0, 0.3 + len(occurrences) * 0.15 + len(field_dicts) * 0.1)
            models.append({
                "name": name,
                "occurrences": len(occurrences),
                "sample_figma_id": sample_id,
                "occurrence_ids": occurrence_ids,
                "fields": field_dicts,
                "field_map": field_map,
                "sample_values": sample,
                "sample_data": sample_data,
                "confidence": round(confidence, 2),
                "suggested_prisma": _prisma_model_code(name, field_dicts),
            })

        models.sort(key=lambda m: (m["confidence"], m["occurrences"]), reverse=True)
        models = models[: self.top_n]
        return {"version": "1", "min_occurrences": self.min_occurrences, "models": models}

    def _walk(self, node: Dict[str, Any]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        if not isinstance(node, dict) or not _is_visible(node):
            return results
        children = node.get("children", [])
        if isinstance(children, list) and len(children) > 0:
            results.append(node)
            for child in children:
                results.extend(self._walk(child))
        return results


def extract_data_models(
    figma_file: str,
    output: str = "data_model.json",
    min_occurrences: int = 2,
    top_n: int = 10,
) -> Dict[str, Any]:
    path = Path(figma_file)
    if not path.exists():
        raise FileNotFoundError(f"Figma node file not found: {figma_file}")
    data = json.loads(path.read_text(encoding="utf-8"))
    root = data if isinstance(data, dict) else data[0] if isinstance(data, list) and data else {}
    extractor = DataModelExtractor(min_occurrences=min_occurrences, top_n=top_n)
    report = extractor.extract(root)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect repeating Figma structures and propose data models.")
    parser.add_argument("--file", default="figma_node.json", help="Path to raw Figma node JSON")
    parser.add_argument("--output", default="data_model.json", help="Output JSON path")
    parser.add_argument("--min-occurrences", type=int, default=2, help="Minimum occurrences to report a model")
    parser.add_argument("--top-n", type=int, default=10, help="Maximum number of proposed models")
    args = parser.parse_args()

    report = extract_data_models(
        figma_file=args.file,
        output=args.output,
        min_occurrences=args.min_occurrences,
        top_n=args.top_n,
    )
    print(f"[DATA-MODEL] {len(report['models'])} candidate model(s) written to {args.output}")
    for model in report["models"]:
        print(f"  - {model['name']} ({model['occurrences']} occurrences, confidence {model['confidence']})")


if __name__ == "__main__":
    main()
