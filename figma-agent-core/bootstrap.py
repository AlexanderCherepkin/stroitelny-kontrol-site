import os
import re
import sys
import time
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

import requests
from dotenv import load_dotenv


OUTPUT_FILE = "figma_node.json"
CACHE_MAX_AGE_MINUTES = 30


def rgba_to_hex(color: Optional[Dict[str, float]]) -> Optional[str]:
    """Конвертирует Figma RGBA (0..1) в HEX строку."""
    if not color:
        return None
    try:
        r = int(round(color.get("r", 0) * 255))
        g = int(round(color.get("g", 0) * 255))
        b = int(round(color.get("b", 0) * 255))
        a = color.get("a", 1.0)
        if a < 1.0:
            a_int = int(round(a * 255))
            return f"#{r:02x}{g:02x}{b:02x}{a_int:02x}"
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return None


def rgba_to_rgb(color: Optional[Dict[str, float]]) -> Optional[str]:
    """Конвертирует Figma RGBA (0..1) в CSS rgb()/rgba() строку."""
    if not color:
        return None
    try:
        r = round(color.get("r", 0) * 255)
        g = round(color.get("g", 0) * 255)
        b = round(color.get("b", 0) * 255)
        a = color.get("a", 1.0)
        if a < 1.0:
            return f"rgba({r}, {g}, {b}, {a:.2f})"
        return f"rgb({r}, {g}, {b})"
    except Exception:
        return None


def extract_fills(fills: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    """Превращает Figma fills в компактный список с HEX/RGB цветами."""
    if not fills:
        return None
    result = []
    for fill in fills:
        fill_type = fill.get("type")
        if fill_type == "SOLID":
            color = fill.get("color")
            result.append({
                "type": "SOLID",
                "hex": rgba_to_hex(color),
                "rgb": rgba_to_rgb(color),
                "opacity": fill.get("opacity", color.get("a", 1.0)) if color else 1.0,
            })
        elif fill_type == "GRADIENT_LINEAR":
            stops = []
            for stop in fill.get("gradientStops", []):
                stops.append({
                    "position": stop.get("position"),
                    "hex": rgba_to_hex(stop.get("color")),
                    "rgb": rgba_to_rgb(stop.get("color")),
                })
            result.append({"type": "GRADIENT_LINEAR", "stops": stops})
        elif fill_type == "IMAGE":
            result.append({"type": "IMAGE", "imageRef": fill.get("imageRef"), "scaleMode": fill.get("scaleMode")})
        else:
            result.append({"type": fill_type})
    return result or None


def extract_effects(effects: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    """Сохраняет тени и размытия в компактном виде."""
    if not effects:
        return None
    result = []
    for effect in effects:
        if not effect.get("visible", True):
            continue
        e_type = effect.get("type")
        if e_type in ("DROP_SHADOW", "INNER_SHADOW"):
            result.append({
                "type": e_type,
                "hex": rgba_to_hex(effect.get("color")),
                "rgb": rgba_to_rgb(effect.get("color")),
                "offset": effect.get("offset"),
                "radius": effect.get("radius"),
                "spread": effect.get("spread"),
            })
        elif e_type == "LAYER_BLUR":
            result.append({"type": "LAYER_BLUR", "radius": effect.get("radius")})
        elif e_type == "BACKGROUND_BLUR":
            result.append({"type": "BACKGROUND_BLUR", "radius": effect.get("radius")})
    return result or None


def extract_text_style(style: Dict[str, Any]) -> Dict[str, Any]:
    """Извлекает ключевые параметры шрифта, включая декорации и гиперссылки."""
    result: Dict[str, Any] = {
        "fontFamily": style.get("fontFamily"),
        "fontSize": style.get("fontSize"),
        "fontWeight": style.get("fontWeight"),
        "lineHeightPx": style.get("lineHeightPx"),
        "letterSpacing": style.get("letterSpacing"),
        "textAlignHorizontal": style.get("textAlignHorizontal"),
        "textAlignVertical": style.get("textAlignVertical"),
        "fills": extract_fills(style.get("fills")),
    }
    for key in ("italic", "textCase", "textDecoration", "hyperlink"):
        if key in style:
            result[key] = style[key]
    return result


class FigmaExtractor:
    def __init__(self, token: str):
        self.headers = {"X-Figma-Token": token}
        self.base_url = "https://api.figma.com/v1"
        self.file_key: Optional[str] = None

    def parse_url(self, url: str) -> Optional[Dict[str, str]]:
        file_key_match = re.search(r"/file/([^/]+)", url) or re.search(r"/design/([^/]+)", url)
        node_id_match = re.search(r"node-id=([^&]+)", url)

        if not file_key_match:
            return None

        return {
            "file_key": file_key_match.group(1),
            "node_id": node_id_match.group(1).replace("-", ":") if node_id_match else "0:1",
        }

    @staticmethod
    def is_structural(node: Dict[str, Any]) -> bool:
        node_type = node.get("type")
        if node_type in ("FRAME", "COMPONENT", "COMPONENT_SET", "INSTANCE"):
            return True
        if node_type == "GROUP" and node.get("children"):
            return True
        if node_type == "TEXT" and node.get("characters"):
            return True
        if node.get("layoutMode"):
            return True
        if node_type in ("RECTANGLE", "ELLIPSE", "VECTOR", "IMAGE"):
            if node.get("fills") or node.get("strokes") or node.get("effects"):
                return True
        return False

    def compress_node(self, node: Dict[str, Any], depth: int = 0, max_depth: int = 8) -> Optional[Dict[str, Any]]:
        if not node.get("visible", True):
            return None

        node_type = node.get("type")
        cleaned: Dict[str, Any] = {
            "id": node.get("id"),
            "name": node.get("name"),
            "type": node_type,
        }

        if "layoutMode" in node:
            cleaned["layoutMode"] = node.get("layoutMode")
            cleaned["layoutPositioning"] = node.get("layoutPositioning")
            cleaned["itemSpacing"] = node.get("itemSpacing")
            cleaned["paddingTop"] = node.get("paddingTop", 0)
            cleaned["paddingRight"] = node.get("paddingRight", 0)
            cleaned["paddingBottom"] = node.get("paddingBottom", 0)
            cleaned["paddingLeft"] = node.get("paddingLeft", 0)
            cleaned["primaryAxisAlignItems"] = node.get("primaryAxisAlignItems")
            cleaned["counterAxisAlignItems"] = node.get("counterAxisAlignItems")
            cleaned["primaryAxisSizingMode"] = node.get("primaryAxisSizingMode")
            cleaned["counterAxisSizingMode"] = node.get("counterAxisSizingMode")
            cleaned["layoutSizingHorizontal"] = node.get("layoutSizingHorizontal")
            cleaned["layoutSizingVertical"] = node.get("layoutSizingVertical")
            cleaned["layoutGrow"] = node.get("layoutGrow")
            cleaned["layoutAlign"] = node.get("layoutAlign")

        if "constraints" in node:
            cleaned["constraints"] = node.get("constraints")

        for sizing_key in ("minWidth", "maxWidth", "minHeight", "maxHeight"):
            if sizing_key in node:
                cleaned[sizing_key] = node.get(sizing_key)

        if "absoluteBoundingBox" in node:
            box = node["absoluteBoundingBox"]
            cleaned["box"] = {
                "x": box.get("x"),
                "y": box.get("y"),
                "width": box.get("width"),
                "height": box.get("height"),
            }

        fills = extract_fills(node.get("fills"))
        if fills:
            cleaned["fills"] = fills
        strokes = extract_fills(node.get("strokes"))
        if strokes:
            cleaned["strokes"] = strokes
        effects = extract_effects(node.get("effects"))
        if effects:
            cleaned["effects"] = effects
        if node.get("cornerRadius"):
            cleaned["cornerRadius"] = node.get("cornerRadius")

        opacity = node.get("opacity")
        if opacity is not None and opacity < 1.0:
            cleaned["opacity"] = opacity

        if node.get("blendMode"):
            cleaned["blendMode"] = node.get("blendMode")

        if node.get("isMask"):
            cleaned["isMask"] = True
            if node.get("maskType"):
                cleaned["maskType"] = node.get("maskType")

        if node.get("booleanOperation"):
            cleaned["booleanOperation"] = node.get("booleanOperation")

        if node_type == "TEXT":
            cleaned["characters"] = node.get("characters", "")
            if "style" in node:
                cleaned["style"] = extract_text_style(node["style"])
            if node.get("styleOverrideTable"):
                cleaned["styleOverrideTable"] = {
                    k: extract_text_style(v)
                    for k, v in node["styleOverrideTable"].items()
                }
            if node.get("characterStyleOverrides"):
                cleaned["characterStyleOverrides"] = list(node["characterStyleOverrides"])

        # Preserve semantic metadata from Figma
        if node.get("description"):
            cleaned["description"] = node["description"]
        if node.get("annotations"):
            cleaned["annotations"] = node["annotations"]

        # Preserve interaction data from Figma prototype
        if node.get("reactions"):
            cleaned["reactions"] = node["reactions"]
        if node.get("variantProperties"):
            cleaned["variantProperties"] = node["variantProperties"]
        if node.get("variantGroupProperties"):
            cleaned["variantGroupProperties"] = node["variantGroupProperties"]
        if node.get("componentSetId"):
            cleaned["componentSetId"] = node["componentSetId"]
        if node.get("componentId"):
            cleaned["componentId"] = node["componentId"]
        if node.get("overrides"):
            cleaned["overrides"] = node["overrides"]

        if node_type in ("RECTANGLE", "ELLIPSE", "VECTOR", "IMAGE"):
            has_image_fill = any(f.get("type") == "IMAGE" for f in (node.get("fills") or []))
            if node_type == "IMAGE" or has_image_fill:
                cleaned["isAsset"] = True
                cleaned["assetFormat"] = "svg" if node_type == "VECTOR" else "png"

        if depth >= max_depth:
            raw_children = [c for c in node.get("children", []) if c.get("visible", True)]
            if raw_children:
                cleaned["children_summary"] = {
                    "count": len(raw_children),
                    "types": list({c.get("type", "UNKNOWN") for c in raw_children}),
                }
            return cleaned

        children: List[Dict[str, Any]] = []
        for child in node.get("children", []):
            if not child.get("visible", True):
                continue
            if not FigmaExtractor.is_structural(child) and not child.get("layoutMode"):
                if not child.get("children"):
                    continue
            compressed = self.compress_node(child, depth + 1, max_depth)
            if compressed:
                children.append(compressed)

        if children:
            cleaned["children"] = children

        return cleaned

    def clean_node_data(self, node: Dict[str, Any], max_depth: int = 8) -> Dict[str, Any]:
        return self.compress_node(node, depth=0, max_depth=max_depth) or {}

    def _fetch_with_retry(
        self, url: str, retries: int = 3, timeout: int = 60
    ) -> requests.Response:
        for attempt in range(retries):
            try:
                response = requests.get(url, headers=self.headers, timeout=timeout)
            except requests.Timeout:
                print(f"Лог: Figma API timeout. Попытка {attempt + 1}/{retries}.")
                if attempt == retries - 1:
                    raise
                continue
            if response.status_code == 200:
                return response
            elif response.status_code == 429:
                wait_time = int(response.headers.get("Retry-After", 10 * (2 ** attempt)))
                print(f"Лог: Figma API rate limit (429). Попытка {attempt + 1}/{retries}. Ждем {wait_time} сек...")
                time.sleep(wait_time)
            else:
                response.raise_for_status()
        raise requests.HTTPError(f"Max retries ({retries}) exceeded for Figma API")

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Возвращает текущий статус rate limit по одному тестовому запросу."""
        if not self.file_key:
            return {"ok": False, "error": "file_key not set"}
        url = f"{self.base_url}/files/{self.file_key}/nodes?ids=0:1&depth=1"
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            return {
                "ok": response.status_code == 200,
                "status": response.status_code,
                "retry_after": response.headers.get("Retry-After"),
                "plan_tier": response.headers.get("X-Figma-Plan-Tier"),
                "rate_limit_type": response.headers.get("X-Figma-Rate-Limit-Type"),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_component_data(
        self,
        url: str,
        node_id: Optional[str] = None,
        depth: Optional[int] = 2,
    ) -> Optional[Dict[str, Any]]:
        params = self.parse_url(url)
        if not params:
            print("Лог: Не удалось распарсить URL. Проверь формат ссылки.")
            return None

        self.file_key = params["file_key"]
        target_node_id = node_id or params["node_id"]
        endpoint = f"{self.base_url}/files/{params['file_key']}/nodes?ids={target_node_id}"
        if depth is not None:
            endpoint += f"&depth={depth}"

        try:
            response = self._fetch_with_retry(endpoint)
        except Exception as e:
            print(f"Лог: не удалось получить данные из Figma API: {e}")
            return None

        raw_data = response.json()
        node_data = raw_data["nodes"][target_node_id]["document"]
        return self.clean_node_data(node_data)


def load_existing_cache() -> Optional[Dict[str, Any]]:
    path = Path(OUTPUT_FILE)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Лог: не удалось прочитать {OUTPUT_FILE}: {e}")
        return None


def cache_age_minutes() -> Optional[float]:
    path = Path(OUTPUT_FILE)
    if not path.exists():
        return None
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - mtime).total_seconds() / 60.0


def save_cache(data: Dict[str, Any]) -> None:
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Лог: структура сохранена в {OUTPUT_FILE}")


def find_node_by_id(root: Dict[str, Any], node_id: str) -> Optional[Dict[str, Any]]:
    if not isinstance(root, dict):
        return None
    if root.get("id") == node_id:
        return root
    for child in root.get("children", []):
        found = find_node_by_id(child, node_id)
        if found:
            return found
    return None


def check_figma_connection(
    force_refresh: bool = False,
    node_id: Optional[str] = None,
    depth: Optional[int] = 2,
) -> bool:
    load_dotenv()

    token = os.environ.get("FIGMA_TOKEN")
    url = os.environ.get("FIGMA_URL")

    if not token or not url:
        print("Ошибка: FIGMA_TOKEN и FIGMA_URL должны быть заданы в файле .env")
        return False

    age = cache_age_minutes()

    if not force_refresh and age is not None and age < CACHE_MAX_AGE_MINUTES:
        print(f"Лог: кеш {OUTPUT_FILE} актуален (возраст {age:.1f} мин). Пропускаем запрос к Figma API.")
        if node_id:
            cached = load_existing_cache()
            if cached:
                target = find_node_by_id(cached, node_id)
                if target:
                    print(f"Лог: найдена нода {node_id} в кеше, используем её.")
                    save_cache(target)
                    return True
                else:
                    print(f"Лог: нода {node_id} не найдена в кеше, будет выполнен запрос к API.")
        else:
            return True

    print(f"Проверка подключения к Figma по адресу: {url}\n")
    extractor = FigmaExtractor(token)
    parsed = extractor.parse_url(url)
    if parsed:
        extractor.file_key = parsed["file_key"]

    status = extractor.get_rate_limit_status()
    if not status.get("ok"):
        retry_after = status.get("retry_after")
        plan_tier = status.get("plan_tier", "unknown")
        rate_type = status.get("rate_limit_type", "unknown")
        if retry_after:
            minutes = int(retry_after) // 60
            print(f"[RATE LIMIT] Figma API временно недоступен ({status.get('status')} 429).")
            print(f"  Plan tier: {plan_tier}, rate limit type: {rate_type}")
            print(f"  Retry-After: {retry_after}s (~{minutes} мин)")
            print(f"  Рекомендация: подожди сброса лимита или используй экспортированный JSON-файл.")
        else:
            print(f"[ERROR] Не удалось проверить статус Figma API: {status}")

        cached = load_existing_cache()
        if cached and not force_refresh:
            print(f"Лог: не удалось обновить данные, но есть кеш. Продолжаем работу с {OUTPUT_FILE}.")
            return True

        print("Не удалось получить данные и нет актуального кеша. Проверь токен/URL или предоставь JSON-файл.")
        return False

    data = extractor.get_component_data(url, node_id=node_id, depth=depth)

    if data:
        print("ПОДКЛЮЧЕНИЕ УСПЕШНО!")
        save_cache(data)
        return True

    if not force_refresh:
        cached = load_existing_cache()
        if cached:
            print(f"Лог: не удалось обновить данные, но есть кеш. Продолжаем работу с {OUTPUT_FILE}.")
            return True

    print("Не удалось получить данные. Проверь токен и URL.")
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Загружает структуру Figma и сохраняет в figma_node.json")
    parser.add_argument("--force", action="store_true", help="Принудительно обновить данные из Figma API")
    parser.add_argument("--refresh", action="store_true", help="Алиас для --force")
    parser.add_argument(
        "--node-id",
        default=None,
        help="ID конкретной ноды Figma для загрузки (пример: 662:808). Если не указан — загружается весь canvas."
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=8,
        help="Максимальная глубина развёртывания дочерних нод при сжатии (по умолчанию 8)."
    )
    parser.add_argument(
        "--api-depth",
        type=int,
        default=2,
        help="Параметр depth для Figma API /nodes (по умолчанию 2). None — без ограничения."
    )
    args = parser.parse_args()

    ok = check_figma_connection(
        force_refresh=args.force or args.refresh,
        node_id=args.node_id,
        depth=args.api_depth,
    )
    sys.exit(0 if ok else 1)
