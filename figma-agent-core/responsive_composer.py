import json
import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Allow standalone execution from any working directory.
sys.path.insert(0, str(Path(__file__).parent))

import analyzer
import layout_engine


_BREAKPOINT_RULES = [
    ("base", ["mobile", "phone"]),
    ("sm", ["small"]),
    ("md", ["tablet"]),
    ("lg", ["laptop"]),
    ("xl", ["desktop", "wide"]),
]


def _load_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _token_for_frame_name(name: str) -> Optional[str]:
    lower = (name or "").lower()
    for token, keywords in _BREAKPOINT_RULES:
        if any(kw in lower for kw in keywords):
            return token
    return None


def _px(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def detect_breakpoint_frames(figma_root: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Находит sibling FRAME'ы верхнего уровня, имена которых соответствуют breakpoint'ам."""
    frames: Dict[str, Dict[str, Any]] = {}
    warnings: List[Dict[str, Any]] = []
    children = figma_root.get("children", [])
    for child in children:
        if child.get("type") not in ("FRAME", "COMPONENT", "INSTANCE", "GROUP"):
            continue
        token = _token_for_frame_name(child.get("name", ""))
        if not token:
            continue
        if token in frames:
            warnings.append({
                "type": "duplicate_breakpoint",
                "token": token,
                "kept_id": frames[token].get("id"),
                "dropped_id": child.get("id"),
            })
            continue
        frames[token] = child
    return frames, warnings


def constraint_to_classes(node: Dict[str, Any]) -> List[str]:
    """Превращает Figma-констрейнты и layoutSizing в Tailwind-классы для базового слоя."""
    classes: List[str] = []
    constraints = node.get("constraints") or {}
    lsh = node.get("layoutSizingHorizontal")
    lsv = node.get("layoutSizingVertical")

    if lsh == "FILL" or constraints.get("horizontal") in ("STRETCH", "LEFT_RIGHT"):
        classes.append("w-full")
    elif lsh == "HUG":
        classes.append("w-auto")

    if lsv == "FILL" or constraints.get("vertical") in ("STRETCH", "TOP_BOTTOM"):
        classes.append("h-full")
    elif lsv == "HUG":
        classes.append("h-auto")

    if node.get("layoutGrow") == 1:
        classes.append("flex-1")
    if node.get("layoutAlign") == "STRETCH":
        classes.append("self-stretch")

    sizing_map = {
        "minWidth": "min-w",
        "maxWidth": "max-w",
        "minHeight": "min-h",
        "maxHeight": "max-h",
    }
    for key, prefix in sizing_map.items():
        value = _px(node.get(key))
        if value is not None and value > 0:
            classes.append(f"{prefix}-[{int(round(value))}px]")

    box = node.get("box") or node.get("absoluteBoundingBox") or {}
    width = _px(box.get("width"))
    height = _px(box.get("height"))
    if lsh == "FIXED" and width is not None and width > 0:
        classes.append(f"w-[{int(round(width))}px]")
    if lsv == "FIXED" and height is not None and height > 0:
        classes.append(f"h-[{int(round(height))}px]")

    return classes


def _find_figma_node(root: Dict[str, Any], node_id: str) -> Optional[Dict[str, Any]]:
    if root.get("id") == node_id:
        return root
    for child in root.get("children", []):
        found = _find_figma_node(child, node_id)
        if found:
            return found
    return None


def _walk_ast_with_index(
    node: Dict[str, Any],
    depth: int = 0,
    sibling_index: int = 0,
):
    """Обходит AST-ноды с тройкой (depth, sibling_index) для резервного сопоставления по имени."""
    yield node, depth, sibling_index
    for idx, child in enumerate(node.get("children", [])):
        yield from _walk_ast_with_index(child, depth + 1, idx)


def _id_key(node: Dict[str, Any]) -> Optional[Tuple[str, Any]]:
    figma_id = node.get("figma_id")
    return ("id", figma_id) if figma_id else None


def _name_key(node: Dict[str, Any], depth: int, sibling_index: int) -> Tuple[Any, ...]:
    name = (node.get("figma_name") or node.get("name") or "").lower()
    return ("name", name, depth, sibling_index)


def _match_key(node: Dict[str, Any], depth: int, sibling_index: int) -> Tuple[Any, ...]:
    """Prefer stable figma_id; fall back to (name, depth, sibling_index)."""
    return _id_key(node) or _name_key(node, depth, sibling_index)


def _build_match_index(ast_root: Dict[str, Any]) -> Dict[Tuple[Any, ...], Dict[str, Any]]:
    index: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for node, depth, sibling_index in _walk_ast_with_index(ast_root):
        key = _match_key(node, depth, sibling_index)
        if key in index:
            continue
        index[key] = node
        # Index both id and name keys when an id is present so lookups can fall back.
        id_key = _id_key(node)
        name_key = _name_key(node, depth, sibling_index)
        if id_key and id_key != key:
            index[id_key] = node
        if name_key and name_key != key:
            index[name_key] = node
    return index


def _lookup_node(
    index: Dict[Tuple[Any, ...], Dict[str, Any]],
    node: Dict[str, Any],
    depth: int,
    sibling_index: int,
) -> Optional[Dict[str, Any]]:
    """Try stable id match first, then fall back to structural name key."""
    id_key = _id_key(node)
    if id_key and id_key in index:
        return index[id_key]
    return index.get(_name_key(node, depth, sibling_index))


def _diff_classes(base_classes: List[str], variant_classes: List[str]) -> List[str]:
    base_set = set(base_classes)
    diffs = [c for c in variant_classes if c not in base_set]
    # Preserve layout-direction changes as responsive variants (e.g. md:flex-row vs flex-col).
    direction_classes = {"flex-row", "flex-col", "flex-wrap", "flex-nowrap", "flex-col-reverse", "flex-row-reverse"}
    base_directions = [c for c in base_classes if c in direction_classes]
    variant_directions = [c for c in variant_classes if c in direction_classes]
    if base_directions != variant_directions:
        for c in variant_directions:
            if c not in diffs:
                diffs.append(c)
    return diffs


def _prefix_classes(classes: List[str], token: str) -> List[str]:
    return [f"{token}:{c}" for c in classes]


def _merge_constraint_classes(
    ast_root: Dict[str, Any],
    figma_root: Dict[str, Any],
) -> Tuple[int, List[Dict[str, Any]]]:
    """Добавляет constraint-классы к базовому AST. Возвращает (count, warnings)."""
    count = 0
    warnings: List[Dict[str, Any]] = []
    for node, _depth, _idx in _walk_ast_with_index(ast_root):
        figma_id = node.get("figma_id")
        if not figma_id:
            continue
        figma_node = _find_figma_node(figma_root, figma_id)
        if not figma_node:
            warnings.append({"type": "missing_figma_node", "figma_id": figma_id})
            continue
        new_classes = constraint_to_classes(figma_node)
        existing = set(node.get("classes", []))
        added = []
        for cls in new_classes:
            if cls not in existing:
                node.setdefault("classes", []).append(cls)
                added.append(cls)
        if added:
            count += len(added)
    return count, warnings


def compose_responsive_ast(
    layout_ast: Dict[str, Any],
    figma_root: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
    base_node_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Главная функция: обогащает layout_ast responsive-вариантами."""
    config = config or {}
    responsive_ast = json.loads(json.dumps(layout_ast))

    breakpoint_frames, warnings = detect_breakpoint_frames(figma_root)
    report: Dict[str, Any] = {
        "breakpoint_frames": {
            token: {
                "id": node.get("id"),
                "name": node.get("name"),
            }
            for token, node in breakpoint_frames.items()
        },
        "matched_nodes": 0,
        "constraint_classes_added": 0,
        "variant_classes_added": 0,
        "warnings": warnings,
    }

    # 1. Базовый constraint-pass.
    constraint_count, constraint_warnings = _merge_constraint_classes(
        responsive_ast.get("root", responsive_ast),
        figma_root,
    )
    report["constraint_classes_added"] = constraint_count
    report["warnings"].extend(constraint_warnings)

    # 2. Определяем базовый фрейм (источник layout_ast).
    base_id = base_node_id
    if not base_id:
        root = responsive_ast.get("root", responsive_ast)
        base_id = root.get("figma_id")

    # 3. Генерация breakpoint-вариантов.
    base_match_index = _build_match_index(responsive_ast.get("root", responsive_ast))
    matched_nodes = 0
    variant_classes_added = 0

    if not breakpoint_frames:
        report["no_breakpoint_variants"] = True

    for token, frame in breakpoint_frames.items():
        if token == "base":
            continue
        if base_id and frame.get("id") == base_id:
            continue

        engine = layout_engine.FigmaLayoutEngine(config)
        result = engine.convert(frame)
        variant_root = result.root.to_dict()

        for variant_node, depth, sibling_index in _walk_ast_with_index(variant_root):
            base_node = _lookup_node(base_match_index, variant_node, depth, sibling_index)
            if not base_node:
                report["warnings"].append({
                    "type": "unmatched_node",
                    "token": token,
                    "figma_id": variant_node.get("figma_id"),
                    "name": variant_node.get("figma_name") or variant_node.get("name"),
                })
                continue

            base_classes = base_node.get("classes", [])
            variant_classes = variant_node.get("classes", [])
            diff = _diff_classes(base_classes, variant_classes)
            if diff:
                prefixed = _prefix_classes(diff, token)
                variants = base_node.setdefault("responsive_variants", {})
                existing = set(variants.get(token, []))
                merged = variants.get(token, []) + [c for c in prefixed if c not in existing]
                variants[token] = merged
                variant_classes_added += len(prefixed)
                matched_nodes += 1

    report["matched_nodes"] = matched_nodes
    report["variant_classes_added"] = variant_classes_added

    return responsive_ast, report


def main():
    parser = argparse.ArgumentParser(description="Responsive Composer: Figma constraints + breakpoint frames → responsive Tailwind AST")
    parser.add_argument("--layout-ast", default="layout_ast.json", help="Путь к Tailwind AST от layout_engine.py")
    parser.add_argument("--figma-file", default="figma_node.json", help="Путь к сжатому JSON Figma-структуры")
    parser.add_argument("--output", default="responsive_ast.json", help="Путь для enriched AST")
    parser.add_argument("--report", default="responsive_report.json", help="Путь для отчёта")
    parser.add_argument("--node-id", default=None, help="ID базового фрейма (источника layout_ast)")
    parser.add_argument("--tokens", default="design_tokens.json", help="Путь к реестру дизайн-токенов")
    parser.add_argument("--assets", default="asset_registry.json", help="Путь к реестру ассетов")
    parser.add_argument("--backend-mapping", default="backend_mapping.json", help="Путь к backend_mapping.json")
    args = parser.parse_args()

    layout_ast = _load_json(args.layout_ast)
    if layout_ast is None:
        print(f"[ERROR] Could not read {args.layout_ast}")
        return

    figma_root = analyzer.load_figma_json(args.figma_file)
    if not figma_root:
        print(f"[ERROR] Could not read {args.figma_file}")
        return

    if args.node_id:
        target = analyzer.find_node_by_id(figma_root, args.node_id)
        if target:
            figma_root = target

    tokens = _load_json(args.tokens)
    assets = _load_json(args.assets)
    backend_mapping = _load_json(args.backend_mapping)
    config: Dict[str, Any] = {}
    if tokens:
        config["tokens"] = tokens
    if assets:
        config["assets"] = assets
    if backend_mapping:
        config["backend_mapping"] = backend_mapping

    responsive_ast, report = compose_responsive_ast(
        layout_ast,
        figma_root,
        config=config,
        base_node_id=args.node_id,
    )

    output_path = Path(args.output)
    output_path.write_text(json.dumps(responsive_ast, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[RESPONSIVE] AST saved to {output_path}")

    report_path = Path(args.report)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[RESPONSIVE] Report saved to {report_path}")


if __name__ == "__main__":
    main()
