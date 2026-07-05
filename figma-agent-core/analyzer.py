
import json
import re
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional


OUTPUT_FILE = "figma_node.json"


GENERIC_NAME_PATTERNS = (
    r"^(Frame|Group|Container|Rectangle|Ellipse|Vector|Text|Component|Instance|Page|Section|Layer)\s*\d*$",
    r"^(Frame|Group|Container|Rectangle|Ellipse|Vector|Text|Component|Instance|Page|Section|Layer)\s*/\s*\d*$",
)


def _clean_name(name: Any) -> str:
    """Remove emoji, special chars, and collapse whitespace."""
    text = str(name or "").strip()
    # Strip common Figma numeric suffixes like "Frame / 1" or "Frame 1".
    text = re.sub(r"\s*/\s*\d+\s*$", "", text).strip()
    text = re.sub(r"\s+\d+\s*$", "", text).strip()
    # Remove emoji and most special characters; keep letters, digits, spaces, hyphens, underscores.
    text = re.sub(r"[^\w\s\-]", " ", text, flags=re.UNICODE)
    # Collapse whitespace.
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_generic_name(name: str) -> bool:
    if not name:
        return True
    for pattern in GENERIC_NAME_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return True
    return False


def _extract_annotation_text(annotations: List[Dict[str, Any]]) -> str:
    """Concatenate annotation labels/descriptions into a semantic hint."""
    parts: List[str] = []
    for annotation in annotations or []:
        label = annotation.get("label") or ""
        description = annotation.get("description") or ""
        if isinstance(label, str):
            parts.append(label.strip())
        if isinstance(description, str):
            parts.append(description.strip())
    return " ".join(p for p in parts if p)


def infer_semantic_name(node: Dict[str, Any], fallback: str = "Component") -> str:
    """Derive a semantic PascalCase name from name, description, and annotations."""
    name = _clean_name(node.get("name", ""))
    description = _clean_name(node.get("description", ""))
    annotations_text = _extract_annotation_text(node.get("annotations"))

    candidates = [name, description, annotations_text]
    chosen = ""
    for candidate in candidates:
        if candidate and not _is_generic_name(candidate):
            chosen = candidate
            break

    if not chosen:
        # Fallback: derive from node type or first meaningful child text.
        node_type = str(node.get("type", fallback)).lower()
        if node_type in ("frame", "group", "component", "instance", "section"):
            chosen = fallback
        else:
            chosen = node_type.capitalize() or fallback

    return _to_pascal_case(chosen)


def _to_pascal_case(name: str) -> str:
    """Convert an arbitrary string to a valid PascalCase identifier."""
    name = name.strip()
    name = re.sub(r"[^\w\s_]+", " ", name)
    name = re.sub(r"[\s_]+", " ", name).strip()
    words = name.split(" ")
    result = "".join(word[:1].upper() + word[1:] for word in words if word)
    result = re.sub(r"[^A-Za-z0-9]+", "", result)
    if not result or not result[0].isalpha():
        result = "Figma" + result
    return result


def load_figma_json(filepath: str = OUTPUT_FILE) -> dict:
    """Загружает кешированный JSON Figma-структуры."""
    path = Path(filepath)
    if not path.exists():
        print(f"Ошибка: Файл {filepath} не найден! Сначала запусти bootstrap.py.")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Ошибка чтения {filepath}: {e}")
        return {}


def find_node_by_id(root: Dict[str, Any], node_id: str) -> Optional[Dict[str, Any]]:
    """Рекурсивно ищет ноду по id в дереве Figma."""
    if not isinstance(root, dict):
        return None
    if root.get("id") == node_id:
        return root
    for child in root.get("children", []):
        found = find_node_by_id(child, node_id)
        if found:
            return found
    return None


def get_node_details(node_id: str, filepath: str = OUTPUT_FILE) -> Optional[Dict[str, Any]]:
    """
    Возвращает очищенную структуру ноды по её id.
    Используется как инструмент агента (FETCH_NODE).
    """
    data = load_figma_json(filepath)
    if not data:
        return None

    node = find_node_by_id(data, node_id)
    if not node:
        return None

    return {
        "id": node.get("id"),
        "name": node.get("name"),
        "semantic_name": infer_semantic_name(node),
        "type": node.get("type"),
        "visible": node.get("visible", True),
        "description": node.get("description") or None,
        "annotations": node.get("annotations") or None,
        "layoutMode": node.get("layoutMode"),
        "itemSpacing": node.get("itemSpacing"),
        "paddingTop": node.get("paddingTop", 0),
        "paddingRight": node.get("paddingRight", 0),
        "paddingBottom": node.get("paddingBottom", 0),
        "paddingLeft": node.get("paddingLeft", 0),
        "primaryAxisAlignItems": node.get("primaryAxisAlignItems"),
        "counterAxisAlignItems": node.get("counterAxisAlignItems"),
        "box": node.get("box"),
        "characters": node.get("characters") if node.get("type") == "TEXT" else None,
        "fontSize": node.get("fontSize"),
        "fontWeight": node.get("fontWeight"),
        "children": [
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "semantic_name": infer_semantic_name(c),
                "type": c.get("type"),
            }
            for c in node.get("children", [])
            if c.get("visible", True)
        ],
    }


def inspect_node(node: dict, depth: int = 0, show_ids: bool = True):
    indent = "  " * depth
    node_type = node.get("type", "UNKNOWN")
    node_name = node.get("name", "Без названия")
    semantic_name = node.get("semantic_name") or infer_semantic_name(node)
    node_id = f" ({node.get('id')})" if show_ids else ""
    semantic_hint = f" [{semantic_name}]" if semantic_name and semantic_name != _to_pascal_case(node_name) else ""

    layout_info = ""
    if node.get("layoutMode"):
        layout_info = f" [AutoLayout: {node['layoutMode']}]"

    text_content = ""
    if node_type == "TEXT" and "characters" in node:
        text_content = f' -> "{node["characters"][:60]}"'

    print(f"{indent}• [{node_type}]{layout_info} {node_name}{node_id}{semantic_hint}{text_content}")

    description = node.get("description")
    if description:
        print(f"{indent}  desc: {description[:120]}")

    annotations = node.get("annotations")
    if annotations:
        annotation_text = _extract_annotation_text(annotations)
        if annotation_text:
            print(f"{indent}  annotations: {annotation_text[:120]}")

    if "children" in node:
        for child in node["children"]:
            inspect_node(child, depth + 1, show_ids=show_ids)


def list_top_level_nodes(node: Dict[str, Any]) -> List[Dict[str, str]]:
    """Возвращает список топ-уровневых нод с id, типом и семантическим именем."""
    return [
        {
            "id": child.get("id"),
            "name": child.get("name"),
            "semantic_name": infer_semantic_name(child),
            "type": child.get("type"),
        }
        for child in node.get("children", [])
        if child.get("visible", True)
    ]


def summarize_tree(node: dict) -> dict:
    """Собирает краткую статистику по дереву."""
    stats = {"nodes": 0, "frames": 0, "texts": 0, "images": 0, "vectors": 0, "auto_layouts": 0, "interactions": 0, "variants": 0}

    def walk(n):
        stats["nodes"] += 1
        t = n.get("type", "UNKNOWN")
        if t == "FRAME":
            stats["frames"] += 1
        elif t == "TEXT":
            stats["texts"] += 1
        elif t in ("RECTANGLE", "ELLIPSE", "IMAGE"):
            stats["images"] += 1
        elif t == "VECTOR":
            stats["vectors"] += 1
        if n.get("layoutMode"):
            stats["auto_layouts"] += 1
        if n.get("reactions"):
            stats["interactions"] += 1
        if n.get("variantProperties"):
            stats["variants"] += 1
        for child in n.get("children", []):
            walk(child)

    walk(node)
    return stats


def main():
    parser = argparse.ArgumentParser(description="Анализатор структуры Figma")
    parser.add_argument(
        "--file",
        default=OUTPUT_FILE,
        help="Путь к JSON-файлу Figma-структуры."
    )
    parser.add_argument(
        "--node-id",
        default=None,
        help="ID конкретной ноды для детального анализа (пример: 662:808)."
    )
    parser.add_argument(
        "--hide-ids",
        action="store_true",
        help="Не показывать ID нод в дереве."
    )
    args = parser.parse_args()

    data = load_figma_json(args.file)
    if not data:
        sys.exit(1)

    if args.node_id:
        target = find_node_by_id(data, args.node_id)
        if not target:
            print(f"Ошибка: нода {args.node_id} не найдена в {args.file}.")
            sys.exit(1)
        print(f"\n=== ДЕТАЛИ НОДЫ {args.node_id} ===")
        inspect_node(target, show_ids=not args.hide_ids)
        stats = summarize_tree(target)
        print("\n=== СТАТИСТИКА ПОДДЕРЕВА ===")
        for key, value in stats.items():
            print(f"  {key}: {value}")
        print("")
        return

    stats = summarize_tree(data)

    print("\n=== ТОП-УРОВНЕВЫЕ СЕКЦИИ ===")
    for node in list_top_level_nodes(data):
        print(f"  [{node['type']}] {node['name']} ({node['id']})")

    print("\n=== СЕМАНТИЧЕСКАЯ КАРТА МАКЕТА ===")
    inspect_node(data, show_ids=not args.hide_ids)
    print("================================\n")

    print("=== СТАТИСТИКА ===")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print("")

    output_path = Path("analysis_report.txt")
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("Figma Analysis Report\n")
            f.write(f"Source: {args.file}\n")
            f.write(f"Canvas: {data.get('name')}\n")
            f.write(f"Stats: {stats}\n\n")
            f.write("Top-level sections:\n")
            for node in list_top_level_nodes(data):
                f.write(f"  - [{node['type']}] {node['name']} ({node['id']})\n")
    except Exception as e:
        print(f"Лог: не удалось сохранить отчёт: {e}")


if __name__ == "__main__":
    main()
