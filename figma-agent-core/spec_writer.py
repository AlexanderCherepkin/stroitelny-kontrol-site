import json
import re
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import analyzer


OUTPUT_FILE = "spec.md"


def _to_pascal_case(name: str) -> str:
    name = name.strip()
    name = re.sub(r"[^\w\s]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    words = name.split(" ")
    result = "".join(word[:1].upper() + word[1:] for word in words if word)
    result = re.sub(r"[^A-Za-z0-9_]+", "", result)
    if not result or not result[0].isalpha():
        result = "Figma" + result
    return result


def _walk(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Обходит дерево и возвращает плоский список нод."""
    if not isinstance(node, dict):
        return []
    results = [node]
    for child in node.get("children", []):
        results.extend(_walk(child))
    return results


def _collect_unique_values(nodes: List[Dict[str, Any]], key: str, transform=None) -> Set[Any]:
    values: Set[Any] = set()
    for node in nodes:
        value = node.get(key)
        if value is None:
            continue
        if transform:
            try:
                value = transform(value)
            except Exception:
                continue
        values.add(value)
    return values


def _collect_fills(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    fills: List[Dict[str, Any]] = []
    for node in nodes:
        raw_fills = node.get("fills", []) or []
        # Поддерживаем как precomputed-объекты bootstrap.py, так и raw Figma fills.
        for fill in raw_fills:
            hex_color = fill.get("hex")
            if hex_color:
                if hex_color.lower() in seen:
                    continue
                seen.add(hex_color.lower())
                fills.append({
                    "hex": hex_color,
                    "rgb": fill.get("rgb"),
                    "context": node.get("name", "unknown"),
                })
                continue
            if fill.get("type") == "SOLID":
                color = fill.get("color")
                if not color:
                    continue
                try:
                    r = int(round(color.get("r", 0) * 255))
                    g = int(round(color.get("g", 0) * 255))
                    b = int(round(color.get("b", 0) * 255))
                    a = color.get("a", 1.0)
                    hex_color = f"#{r:02x}{g:02x}{b:02x}" if a >= 1.0 else f"#{r:02x}{g:02x}{b:02x}{int(round(a * 255)):02x}"
                except Exception:
                    continue
                if hex_color.lower() in seen:
                    continue
                seen.add(hex_color.lower())
                fills.append({
                    "hex": hex_color,
                    "rgb": f"rgb({r}, {g}, {b})" if a >= 1.0 else f"rgba({r}, {g}, {b}, {a:.2f})",
                    "context": node.get("name", "unknown"),
                })
    return fills


def _collect_typography(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    typography: List[Dict[str, Any]] = []
    for node in nodes:
        if node.get("type") != "TEXT":
            continue
        style = node.get("style", {})
        font_family = style.get("fontFamily") or node.get("fontFamily")
        font_size = style.get("fontSize") or node.get("fontSize")
        font_weight = style.get("fontWeight") or node.get("fontWeight")
        if not font_size:
            continue
        key = f"{font_family}|{font_size}|{font_weight}"
        if key in seen:
            continue
        seen.add(key)
        typography.append({
            "fontFamily": font_family or "Unknown",
            "fontSize": font_size,
            "fontWeight": font_weight or 400,
            "example": node.get("characters", "")[:60],
        })
    typography.sort(key=lambda t: (t["fontSize"], t["fontWeight"]), reverse=True)
    return typography


def _collect_components(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    components: List[Dict[str, Any]] = []
    for node in nodes:
        node_type = node.get("type")
        if node_type in ("COMPONENT", "COMPONENT_SET", "INSTANCE"):
            components.append({
                "id": node.get("id"),
                "name": node.get("name"),
                "type": node_type,
            })
    return components


def _collect_assets(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    assets: List[Dict[str, Any]] = []
    for node in nodes:
        if node.get("isAsset") or node.get("type") in ("IMAGE", "VECTOR"):
            assets.append({
                "id": node.get("id"),
                "name": node.get("name"),
                "type": node.get("type"),
                "format": node.get("assetFormat", "png"),
            })
    return assets


def _extract_layout_rules(node: Dict[str, Any], depth: int = 0) -> List[str]:
    rules: List[str] = []
    indent = "  " * depth
    name = node.get("name", "Unnamed")
    node_type = node.get("type", "UNKNOWN")
    layout_mode = node.get("layoutMode")

    if layout_mode:
        direction = "vertical" if layout_mode == "VERTICAL" else "horizontal"
        spacing = node.get("itemSpacing", 0)
        padding = f"pt={node.get('paddingTop', 0)} pr={node.get('paddingRight', 0)} pb={node.get('paddingBottom', 0)} pl={node.get('paddingLeft', 0)}"
        rules.append(
            f"{indent}- [{node_type}] **{name}**: AutoLayout {direction}, "
            f"spacing={spacing}px, padding ({padding})"
        )
    elif node_type in ("FRAME", "COMPONENT", "INSTANCE", "GROUP"):
        rules.append(f"{indent}- [{node_type}] **{name}**: container/frame")

    if node_type == "TEXT":
        text = node.get("characters", "")
        style = node.get("style", {})
        rules.append(
            f"{indent}  - Text: \"{text[:80]}\" "
            f"(font={style.get('fontFamily', 'unknown')}, size={style.get('fontSize')}, weight={style.get('fontWeight')})"
        )

    for child in node.get("children", []):
        rules.extend(_extract_layout_rules(child, depth + 1))

    return rules


def _build_page_tree(node: Dict[str, Any], depth: int = 0) -> List[str]:
    lines: List[str] = []
    indent = "  " * depth
    name = node.get("name", "Unnamed")
    node_type = node.get("type", "UNKNOWN")
    node_id = node.get("id", "")
    lines.append(f"{indent}- **{name}** ({node_type}, id: `{node_id}`)")
    for child in node.get("children", []):
        lines.extend(_build_page_tree(child, depth + 1))
    return lines


def generate_spec(node: Dict[str, Any], output_path: str = OUTPUT_FILE) -> str:
    """Генерирует Markdown-спецификацию на основе Figma-ноды и сохраняет в файл."""
    nodes = _walk(node)
    root_name = node.get("name", "Figma Design")
    root_id = node.get("id", "unknown")
    component_name = _to_pascal_case(root_name)

    colors = _collect_fills(nodes)
    typography = _collect_typography(nodes)
    components = _collect_components(nodes)
    assets = _collect_assets(nodes)
    layout_rules = _extract_layout_rules(node)
    page_tree = _build_page_tree(node)

    lines: List[str] = []
    lines.append(f"# Техническое задание: {root_name}")
    lines.append("")
    lines.append(f"- **ID ноды:** `{root_id}`")
    lines.append(f"- **Имя компонента (PascalCase):** `{component_name}`")
    lines.append("")

    lines.append("## 1. Общее описание")
    lines.append("")
    lines.append(f"Макет `{root_name}` содержит {len(nodes)} нод(ы). "
                 f"Необходимо реализовать веб-страницу/секцию, максимально приближенную к дизайну Figma.")
    lines.append("")

    lines.append("## 2. Структура страницы")
    lines.append("")
    lines.extend(page_tree)
    lines.append("")

    lines.append("## 3. Цветовая палитра")
    lines.append("")
    if colors:
        lines.append("| HEX | RGB | Где используется |")
        lines.append("| --- | --- | ---------------- |")
        for color in colors:
            lines.append(f"| {color['hex']} | {color['rgb']} | {color['context']} |")
    else:
        lines.append("Цветовая информация не найдена.")
    lines.append("")

    lines.append("## 4. Типографика")
    lines.append("")
    if typography:
        lines.append("| Шрифт | Размер | Вес | Пример текста |")
        lines.append("| ----- | ------ | --- | ------------- |")
        for t in typography:
            example = t['example'].replace('|', '\\|')
            lines.append(f"| {t['fontFamily']} | {t['fontSize']}px | {t['fontWeight']} | {example} |")
    else:
        lines.append("Текстовые стили не найдены.")
    lines.append("")

    lines.append("## 5. Layout и отступы")
    lines.append("")
    lines.append("```")
    lines.extend(layout_rules)
    lines.append("```")
    lines.append("")

    if components:
        lines.append("## 6. Компоненты Figma")
        lines.append("")
        lines.append("| ID | Имя | Тип |")
        lines.append("| -- | --- | --- |")
        for c in components:
            lines.append(f"| {c['id']} | {c['name']} | {c['type']} |")
        lines.append("")

    if assets:
        lines.append("## 7. Ассеты (изображения / векторы)")
        lines.append("")
        lines.append("| ID | Имя | Тип | Формат |")
        lines.append("| -- | --- | --- | ------ |")
        for a in assets:
            lines.append(f"| {a['id']} | {a['name']} | {a['type']} | {a['format']} |")
        lines.append("")

    lines.append("## 8. Требования к фронтенду")
    lines.append("")
    lines.append("- Использовать React + Next.js + TypeScript.")
    lines.append("- Стилизация через Tailwind CSS.")
    lines.append("- Цвета и шрифты должны соответствовать таблицам выше.")
    lines.append("- Layout, padding и spacing должны соответствовать AutoLayout Figma.")
    lines.append("- Ассеты должны быть сохранены в `public/images/` и подключены через `<img>`.")
    lines.append("- Компонент должен быть семантичным и доступным (a11y).")
    lines.append("")

    lines.append("## 9. Предполагаемые требования к бэкенду")
    lines.append("")
    lines.append("На основе дизайна однозначно определить бэкенд невозможно. "
                 "Ниже — типовые эндпоинты, которые могут понадобиться для страницы такого типа:")
    lines.append("")
    lines.append("- `GET /api/content/{section}` — получение текстового контента секций.")
    lines.append("- `GET /api/assets` — список медиа-ассетов для страницы.")
    lines.append("- `POST /api/contact` или `POST /api/lead` — если в дизайне есть формы.")
    lines.append("")
    lines.append("Для точного ТЗ на бэкенд необходимо указать:")
    lines.append("- бизнес-логику страницы,")
    lines.append("- источники данных,")
    lines.append("- сценарии взаимодействия пользователя.")
    lines.append("")

    lines.append("## 10. Рекомендуемые следующие шаги")
    lines.append("")
    lines.append(f"1. Запустить генерацию компонента: `python agent.py --node-id {root_id}`")
    lines.append(f"2. Скачать ассеты: `python asset_downloader.py` (или через `agent.py` без `--skip-assets`)")
    lines.append(f"3. Проверить результат в `components/{component_name}.tsx`.")
    lines.append("")

    content = "\n".join(lines)
    path = Path(output_path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return str(path)


def main():
    parser = argparse.ArgumentParser(description="Генератор технического задания по Figma-ноде")
    parser.add_argument(
        "--file",
        default="figma_node.json",
        help="Путь к JSON-файлу Figma-структуры"
    )
    parser.add_argument(
        "--node-id",
        default=None,
        help="ID конкретной ноды для анализа (пример: 662:808)"
    )
    parser.add_argument(
        "--output",
        default=OUTPUT_FILE,
        help="Путь для сохранения Markdown-спецификации"
    )
    args = parser.parse_args()

    data = analyzer.load_figma_json(args.file)
    if not data:
        print(f"Ошибка: не удалось загрузить {args.file}")
        return

    node = data
    if args.node_id:
        target = analyzer.find_node_by_id(data, args.node_id)
        if not target:
            print(f"Ошибка: нода {args.node_id} не найдена в {args.file}")
            return
        node = target

    output_path = generate_spec(node, output_path=args.output)
    print(f"[SPEC] Saved specification to: {output_path}")


if __name__ == "__main__":
    main()
