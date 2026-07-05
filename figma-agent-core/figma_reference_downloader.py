import argparse
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import unquote

import requests
from dotenv import load_dotenv


load_dotenv()


DEFAULT_OUTPUT = ".tmp/browser/figma_reference.png"
DEFAULT_SCALE = 2.0
DEFAULT_FORMAT = "png"
POLL_INTERVAL_SECONDS = 1.0
MAX_POLL_ATTEMPTS = 30


def _parse_file_key(source: str) -> Optional[str]:
    if not source:
        return None
    match = re.search(r"/file/([^/?#]+)", source) or re.search(r"/design/([^/?#]+)", source)
    if match:
        return unquote(match.group(1))
    stripped = source.strip()
    if re.fullmatch(r"[A-Za-z0-9_\-]+", stripped):
        return stripped
    return None


def _sanitize_output_dir(output_path: str, root_dir: Optional[str] = None) -> Path:
    target = Path(output_path).resolve()
    root = Path(root_dir).resolve() if root_dir else Path.cwd().resolve()
    if not str(target).startswith(str(root)):
        raise ValueError(f"Output path outside workspace: {output_path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _resolve_image_url(response_data: Dict[str, Any], node_id: str) -> Optional[str]:
    images = response_data.get("images", {})
    value = images.get(node_id)
    if isinstance(value, dict):
        return value.get("url")
    if isinstance(value, str) and value.startswith("http"):
        return value
    return None


class FigmaReferenceDownloader:
    """Скачивает референсный скриншот Figma-фрейма через Figma Images API."""

    def __init__(
        self,
        token: Optional[str] = None,
        file_key: Optional[str] = None,
        url: Optional[str] = None,
    ):
        self.token = token or os.environ.get("FIGMA_TOKEN")
        self.file_key = file_key or _parse_file_key(url or os.environ.get("FIGMA_URL", ""))

    def download(
        self,
        node_id: str,
        output_path: str = DEFAULT_OUTPUT,
        scale: float = DEFAULT_SCALE,
        fmt: str = DEFAULT_FORMAT,
        root_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        target = _sanitize_output_dir(output_path, root_dir=root_dir)

        if not self.file_key:
            return self._error("Figma file key not provided and FIGMA_URL not set")
        if not self.token:
            return self._error("Figma token not provided and FIGMA_TOKEN not set")
        if not node_id:
            return self._error("node_id is required")

        ids_param = node_id.replace(":", "%3A")
        endpoint = (
            f"https://api.figma.com/v1/images/{self.file_key}"
            f"?ids={ids_param}&format={fmt}&scale={scale}"
        )

        try:
            response = requests.get(
                endpoint,
                headers={"X-Figma-Token": self.token},
                timeout=60,
            )
        except Exception as e:
            return self._error(f"Figma Images API request failed: {e}")

        if response.status_code != 200:
            return self._error(
                f"Figma Images API returned {response.status_code}: {response.text}"
            )

        data = response.json()
        if data.get("err"):
            return self._error(f"Figma API error: {data.get('err')}")

        image_url = _resolve_image_url(data, node_id)
        if not image_url:
            return self._error(f"No image URL returned for node {node_id}")

        polled_url = self._poll_image_url(image_url)
        if not polled_url:
            return self._error("Figma image rendering did not complete in time")

        try:
            download_response = requests.get(polled_url, timeout=120)
        except Exception as e:
            return self._error(f"Failed to download image: {e}")

        if download_response.status_code != 200:
            return self._error(
                f"Image download returned {download_response.status_code}"
            )

        target.write_bytes(download_response.content)

        width, height = self._image_dimensions(download_response.content, fmt)
        return {
            "success": True,
            "path": str(target),
            "width": width,
            "height": height,
            "node_id": node_id,
            "file_key": self.file_key,
            "scale": scale,
            "format": fmt,
            "error": None,
        }

    def _poll_image_url(self, url: str) -> Optional[str]:
        if not url.endswith(":pending"):
            return url
        for _ in range(MAX_POLL_ATTEMPTS):
            time.sleep(POLL_INTERVAL_SECONDS)
            try:
                response = requests.head(url, timeout=10, allow_redirects=True)
                if response.status_code == 200 and not response.url.endswith(":pending"):
                    return response.url
            except Exception:
                pass
        return None

    def _image_dimensions(self, content: bytes, fmt: str) -> Tuple[Optional[int], Optional[int]]:
        if fmt.lower() != "png":
            return None, None
        try:
            width = int.from_bytes(content[16:20], byteorder="big")
            height = int.from_bytes(content[20:24], byteorder="big")
            return width, height
        except Exception:
            return None, None

    def _error(self, message: str) -> Dict[str, Any]:
        return {
            "success": False,
            "path": None,
            "width": None,
            "height": None,
            "node_id": None,
            "file_key": self.file_key,
            "scale": DEFAULT_SCALE,
            "format": DEFAULT_FORMAT,
            "error": message,
        }


def download_figma_reference(
    node_id: str,
    output_path: str = DEFAULT_OUTPUT,
    scale: float = DEFAULT_SCALE,
    fmt: str = DEFAULT_FORMAT,
    token: Optional[str] = None,
    file_key: Optional[str] = None,
    url: Optional[str] = None,
    root_dir: Optional[str] = None,
) -> Dict[str, Any]:
    downloader = FigmaReferenceDownloader(token=token, file_key=file_key, url=url)
    return downloader.download(
        node_id=node_id,
        output_path=output_path,
        scale=scale,
        fmt=fmt,
        root_dir=root_dir,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download a Figma reference screenshot via Figma Images API"
    )
    parser.add_argument("--node-id", required=True, help="Figma node id to render")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output PNG path")
    parser.add_argument("--scale", type=float, default=DEFAULT_SCALE, help="Image scale")
    parser.add_argument("--format", default=DEFAULT_FORMAT, help="Image format")
    parser.add_argument("--token", default=None, help="Figma API token")
    parser.add_argument("--file-key", default=None, help="Figma file key")
    parser.add_argument("--url", default=None, help="Figma file URL")
    parser.add_argument("--root-dir", default=None, help="Workspace root for path guard")
    args = parser.parse_args()

    result = download_figma_reference(
        node_id=args.node_id,
        output_path=args.output,
        scale=args.scale,
        fmt=args.format,
        token=args.token,
        file_key=args.file_key,
        url=args.url,
        root_dir=args.root_dir,
    )
    print(result)


if __name__ == "__main__":
    main()
