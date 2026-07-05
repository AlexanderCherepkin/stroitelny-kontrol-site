import os
import re
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_PUBLIC_DIR = "public"
DEFAULT_IMAGES_DIR = "images"


def _load_asset_pipeline():
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("figma_asset_pipeline", str(here / "asset_pipeline.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _safe_filename(name: str, extension: str) -> str:
    """Превращает имя ноды в безопасное имя файла."""
    base = name.replace(".", "_").replace(" ", "_")
    base = re.sub(r"[^A-Za-z0-9_\-]", "", base)
    if not base:
        base = "asset"
    return f"{base}.{extension}"


def download_asset(url: str, dest_path: Path, timeout: int = 60) -> bool:
    """Скачивает ассет по URL и сохраняет в dest_path."""
    try:
        module = _load_asset_pipeline()
        downloader = module.AssetDownloader()
        return downloader.download(url, dest_path)
    except Exception:
        # Fallback для обратной совместимости: простой requests.get.
        import requests

        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code != 200:
                return False
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as f:
                f.write(response.content)
            return True
        except Exception:
            return False


def save_asset(node_id: str, node_name: str, extension: str, image_url: str, public_dir: str = DEFAULT_PUBLIC_DIR) -> str:
    """
    Скачивает ассет и сохраняет его в public/images/.
    Возвращает путь, который можно использовать в Next.js-компоненте (начинается с /).
    """
    images_dir = Path(public_dir) / DEFAULT_IMAGES_DIR
    filename = _safe_filename(node_name, extension)
    # Добавляем уникальность по node_id, если имя совпадает.
    unique_name = f"{Path(filename).stem}_{node_id.replace(':', '_')}{Path(filename).suffix}"
    dest_path = images_dir / unique_name

    if download_asset(image_url, dest_path):
        return f"/{DEFAULT_IMAGES_DIR}/{unique_name}"
    return ""


def get_image_urls_from_figma(
    file_key: str,
    node_ids: List[str],
    figma_token: str,
    scale: float = 1.0,
    format: str = "png",
) -> Dict[str, str]:
    """
    Запрашивает URL'ы экспорта ассетов через Figma Images API.
    Возвращает {node_id: image_url}.
    """
    if not node_ids:
        return {}
    try:
        module = _load_asset_pipeline()
        downloader = module.AssetDownloader(token=figma_token, url=f"https://www.figma.com/file/{file_key}")
        return downloader.get_image_urls(node_ids, fmt=format, scale=scale)
    except Exception as e:
        print(f"[ERROR] Failed to fetch image URLs: {e}")
        return {}


def collect_assets_from_tree(node: Dict, result: Optional[List[Dict]] = None) -> List[Dict]:
    """Рекурсивно собирает все ноды, помеченные как isAsset."""
    if result is None:
        result = []
    if not isinstance(node, dict) or not node.get("visible", True):
        return result
    if node.get("isAsset"):
        result.append(node)
    for child in node.get("children", []):
        collect_assets_from_tree(child, result)
    return result
