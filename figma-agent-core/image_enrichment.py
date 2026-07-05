"""Fallback image enrichment for card-like data models.

Reads data_model.json, tries to reuse real Figma assets, and falls back to an
external image provider (Unsplash by default) for rows whose imageUrl is empty.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


DEFAULT_OUTPUT_DIR = "public/assets/enriched"
DEFAULT_REGISTRY_FILE = "enriched_image_registry.json"
DEFAULT_PROVIDER = "unsplash"
DEFAULT_MAX_IMAGES = 20
DEFAULT_DELAY = 1.0
DEFAULT_IMAGE_FORMAT = "jpg"


_STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "of", "for", "with", "to", "in",
    "on", "at", "from", "by", "as", "is", "are", "was", "were", "be", "been",
    "this", "that", "these", "those", "our", "your", "my", "their", "its",
    "we", "you", "they", "i", "he", "she", "it", "am", "have", "has", "had",
    "will", "would", "could", "should", "can", "may", "might", "shall",
}


def _safe_name(name: Any) -> str:
    return re.sub(r"[^\w\-]", "_", str(name or "unnamed")).strip("_") or "unnamed"


def _safe_filename(name: str) -> str:
    base = name.replace(".", "_").replace(" ", "_").replace(":", "_")
    base = re.sub(r"[^A-Za-z0-9_\-]", "", base)
    if not base:
        base = "enriched"
    return base[:64]


def _public_path(dest: Path, output_dir: Path) -> str:
    """Return a site-root URL path for a downloaded image."""
    output_dir = output_dir.resolve()
    dest = dest.resolve()
    parts = output_dir.parts
    if "public" in parts:
        idx = parts.index("public")
        public_root = Path(*parts[: idx + 1])
        try:
            return "/" + dest.relative_to(public_root).as_posix()
        except ValueError:
            pass
    return _public_path(dest, self.output_dir)


def _find_node_by_id(root: Dict[str, Any], node_id: str) -> Optional[Dict[str, Any]]:
    if root.get("id") == node_id:
        return root
    for child in root.get("children", []):
        found = _find_node_by_id(child, node_id)
        if found:
            return found
    return None


def _collect_image_refs(node: Dict[str, Any]) -> List[str]:
    refs: List[str] = []
    if node.get("type") == "IMAGE":
        refs.append(node.get("id", ""))
    for fill in node.get("fills", []) or []:
        if fill.get("type") == "IMAGE":
            ref = fill.get("imageRef", "")
            if ref:
                refs.append(ref)
    for child in node.get("children", []):
        refs.extend(_collect_image_refs(child))
    return [r for r in refs if r]


class ImageProvider(ABC):
    @abstractmethod
    def search_images(self, query: str, count: int = 1) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def download_image(self, url: str, dest: Path) -> bool:
        ...


class UnsplashProvider(ImageProvider):
    API_ROOT = "https://api.unsplash.com"

    def __init__(self, access_key: str, request_delay: float = DEFAULT_DELAY) -> None:
        self.access_key = access_key
        self.request_delay = request_delay
        self._last_request_time: Optional[float] = None
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Client-ID {access_key}",
            "Accept-Version": "v1",
        })

    def _throttle(self) -> None:
        if self.request_delay <= 0 or self._last_request_time is None:
            self._last_request_time = time.monotonic()
            return
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self._last_request_time = time.monotonic()

    def search_images(self, query: str, count: int = 1) -> List[Dict[str, Any]]:
        self._throttle()
        url = f"{self.API_ROOT}/search/photos"
        params = {"query": query, "per_page": max(1, min(count, 30))}
        try:
            response = self._session.get(url, params=params, timeout=30)
            response.raise_for_status()
        except Exception as e:
            print(f"[IMAGE-ENRICH] Unsplash search failed: {e}")
            return []

        results: List[Dict[str, Any]] = []
        for item in response.json().get("results", []):
            urls = item.get("urls", {})
            user = item.get("user", {})
            links = item.get("links", {})
            result = {
                "url": urls.get("regular") or urls.get("small"),
                "thumb_url": urls.get("small") or urls.get("thumb"),
                "source_name": "Unsplash",
                "source_url": links.get("html", ""),
                "author_name": user.get("name", ""),
                "author_url": user.get("links", {}).get("html", ""),
                "width": item.get("width"),
                "height": item.get("height"),
            }
            if result["url"]:
                results.append(result)
        return results

    def download_image(self, url: str, dest: Path) -> bool:
        try:
            response = self._session.get(url, timeout=60)
            response.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(response.content)
            return True
        except Exception as e:
            print(f"[IMAGE-ENRICH] Download failed: {e}")
            return False


class PollinationsProvider(ImageProvider):
    """Provider that generates on-demand images via Pollinations AI.

    No API key is required. The provider turns the search query into an image
    generation prompt and returns a direct download URL. Width/height default to
    common card sizes; they can be overridden via constructor.
    """

    API_ROOT = "https://image.pollinations.ai/prompt"

    def __init__(
        self,
        width: int = 360,
        height: int = 160,
        request_delay: float = DEFAULT_DELAY,
        nologo: bool = True,
    ) -> None:
        self.width = width
        self.height = height
        self.request_delay = request_delay
        self.nologo = nologo
        self._last_request_time: Optional[float] = None
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; AgenticLoopImageEnricher/1.0)",
        })

    def _throttle(self) -> None:
        if self.request_delay <= 0 or self._last_request_time is None:
            self._last_request_time = time.monotonic()
            return
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self._last_request_time = time.monotonic()

    @staticmethod
    def _escape_prompt(query: str) -> str:
        return re.sub(r"[^\w\s,\-]", "", query).strip().replace(" ", "%20")

    def search_images(self, query: str, count: int = 1) -> List[Dict[str, Any]]:
        self._throttle()
        if not query:
            return []
        prompt = self._escape_prompt(query)
        results: List[Dict[str, Any]] = []
        for i in range(count):
            url = (
                f"{self.API_ROOT}/{prompt}"
                f"?width={self.width}&height={self.height}"
                f"&seed={abs(hash(query + str(i))) % 100000}"
            )
            if self.nologo:
                url += "&nologo=true"
            results.append({
                "url": url,
                "thumb_url": url,
                "source_name": "Pollinations AI",
                "source_url": "https://pollinations.ai",
                "author_name": "",
                "author_url": "",
            })
        return results

    def download_image(self, url: str, dest: Path) -> bool:
        try:
            self._throttle()
            response = self._session.get(url, timeout=120)
            response.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(response.content)
            return True
        except Exception as e:
            print(f"[IMAGE-ENRICH] Pollinations download failed: {e}")
            return False


class MockImageProvider(ImageProvider):
    """Provider for tests: returns a tiny 1x1 PNG and copies it on download."""

    def __init__(self, image_path: Optional[str] = None) -> None:
        self.image_path = Path(image_path) if image_path else None

    def search_images(self, query: str, count: int = 1) -> List[Dict[str, Any]]:
        return [{
            "url": str(self.image_path) if self.image_path else "mock://image.png",
            "thumb_url": "",
            "source_name": "Mock",
            "source_url": "",
            "author_name": "",
            "author_url": "",
        }] * count

    def download_image(self, url: str, dest: Path) -> bool:
        if self.image_path and self.image_path.exists():
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(self.image_path.read_bytes())
                return True
            except Exception:
                return False
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xdc\xcc\xd9\xa0\x00\x00\x00\x00IEND\xaeB`\x82")
            return True
        except Exception:
            return False


class QueryBuilder:
    def __init__(self, page_context: str = "") -> None:
        self.page_context = page_context.strip().lower()

    def build_query(self, row: Dict[str, Any], model_name: str = "") -> str:
        candidates: List[str] = []
        for key in ("title", "name", "heading", "headline", "label", "subtitle", "description", "text"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())
        if not candidates and model_name:
            candidates.append(model_name)

        raw = " ".join(candidates).lower()
        words = re.findall(r"[a-z0-9]+", raw)
        filtered = [w for w in words if w not in _STOP_WORDS and len(w) > 2]
        if self.page_context:
            context_words = re.findall(r"[a-z0-9]+", self.page_context)
            for w in context_words[:3]:
                if w not in _STOP_WORDS and w not in filtered:
                    filtered.append(w)
        unique: List[str] = []
        for w in filtered:
            if w not in unique:
                unique.append(w)
        return " ".join(unique[:6])

    def build_alt(self, row: Dict[str, Any], query: str = "") -> str:
        for key in ("title", "name", "heading", "headline", "label"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:120]
        if query:
            return query[:120]
        return "Image"


class LocalAssetResolver:
    def __init__(self, figma_data: Dict[str, Any], asset_registry: Optional[Dict[str, Any]]) -> None:
        self.figma_data = figma_data
        self.asset_registry = asset_registry

    def resolve(self, node_id: str) -> Optional[Dict[str, Any]]:
        node = _find_node_by_id(self.figma_data, node_id)
        if not node:
            return None
        refs = _collect_image_refs(node)
        if not self.asset_registry:
            return None
        assets = self.asset_registry.get("assets", {})
        for ref in refs:
            entry = assets.get(ref)
            if entry and entry.get("publicPath"):
                return entry
        return None


class DataModelEnricher:
    def __init__(
        self,
        provider: ImageProvider,
        output_dir: Path,
        max_images: int = DEFAULT_MAX_IMAGES,
        skip_existing: bool = True,
    ) -> None:
        self.provider = provider
        self.output_dir = output_dir
        self.max_images = max_images
        self.skip_existing = skip_existing
        self._query_builder = QueryBuilder()
        self._resolver: Optional[LocalAssetResolver] = None
        self._downloaded = 0
        self._reused = 0
        self._skipped = 0

    def enrich(
        self,
        data_model: Dict[str, Any],
        figma_data: Optional[Dict[str, Any]] = None,
        asset_registry: Optional[Dict[str, Any]] = None,
        page_context: str = "",
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        if figma_data:
            self._resolver = LocalAssetResolver(figma_data, asset_registry)
        self._query_builder = QueryBuilder(page_context)

        models = data_model.get("models", [])
        enriched_entries: List[Dict[str, Any]] = []

        for model in models:
            image_field = self._image_field_name(model)
            if not image_field:
                continue

            sample_data = model.get("sample_data", []) or []
            occurrence_ids = model.get("occurrence_ids", [])
            field_map = model.get("field_map", {})
            alt_field = field_map.get("imageAlt")
            if not alt_field:
                alt_field = "imageAlt"
                field_map["imageAlt"] = alt_field
                model["fields"].append({"name": alt_field, "type": "String"})

            enriched_rows: List[Dict[str, Any]] = []
            for idx, row in enumerate(sample_data):
                if not isinstance(row, dict):
                    row = {}
                entry = self._enrich_row(
                    row,
                    image_field,
                    alt_field,
                    occurrence_ids[idx] if idx < len(occurrence_ids) else None,
                    model.get("name", "Item"),
                    idx,
                )
                enriched_rows.append(entry)
                if entry.get("source"):
                    enriched_entries.append(entry)

            model["sample_data"] = enriched_rows
            model["field_map"] = field_map

        return data_model, enriched_entries

    def _image_field_name(self, model: Dict[str, Any]) -> Optional[str]:
        field_map = model.get("field_map", {})
        if "imageUrl" in field_map.values():
            for k, v in field_map.items():
                if v == "imageUrl":
                    return k
        for f in model.get("fields", []):
            if f.get("name", "").lower().endswith("imageurl") or f.get("name", "").lower() == "image":
                return f["name"]
        return None

    def _enrich_row(
        self,
        row: Dict[str, Any],
        image_field: str,
        alt_field: str,
        occurrence_id: Optional[str],
        model_name: str,
        idx: int,
    ) -> Dict[str, Any]:
        if self.skip_existing and row.get(image_field):
            self._skipped += 1
            return row

        if self._resolver and occurrence_id:
            local = self._resolver.resolve(occurrence_id)
            if local and local.get("publicPath"):
                row[image_field] = local["publicPath"]
                row[alt_field] = self._query_builder.build_alt(row)
                self._reused += 1
                return row

        if self._downloaded >= self.max_images:
            return row

        query = self._query_builder.build_query(row, model_name)
        if not query:
            return row

        results = self.provider.search_images(query, count=3)
        if not results:
            return row

        chosen = results[0]
        ext = Path(chosen["url"].split("?")[0]).suffix.lstrip(".").lower() or DEFAULT_IMAGE_FORMAT
        if ext not in ("jpg", "jpeg", "png", "webp"):
            ext = DEFAULT_IMAGE_FORMAT
        query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:8]
        filename = f"{_safe_filename(model_name)}_{idx}_{query_hash}.{ext}"
        dest = self.output_dir / filename

        if self.skip_existing and dest.exists():
            row[image_field] = _public_path(dest, self.output_dir)
        else:
            if not self.provider.download_image(chosen["url"], dest):
                return row
            row[image_field] = _public_path(dest, self.output_dir)

        row[alt_field] = self._query_builder.build_alt(row, query)
        self._downloaded += 1
        return row


class ImageEnrichmentPipeline:
    def __init__(
        self,
        provider: ImageProvider,
        output_dir: str = DEFAULT_OUTPUT_DIR,
        max_images: int = DEFAULT_MAX_IMAGES,
        skip_existing: bool = True,
    ) -> None:
        self.provider = provider
        self.output_dir = Path(output_dir).resolve()
        self.max_images = max_images
        self.skip_existing = skip_existing

    def run(
        self,
        data_model: Dict[str, Any],
        figma_data: Optional[Dict[str, Any]] = None,
        asset_registry: Optional[Dict[str, Any]] = None,
        page_context: str = "",
    ) -> Dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        enricher = DataModelEnricher(
            provider=self.provider,
            output_dir=self.output_dir,
            max_images=self.max_images,
            skip_existing=self.skip_existing,
        )
        enriched_model, entries = enricher.enrich(
            data_model,
            figma_data=figma_data,
            asset_registry=asset_registry,
            page_context=page_context,
        )
        registry = {
            "version": "1",
            "provider": getattr(self.provider, "__class__.__name__", "unknown"),
            "output_dir": str(self.output_dir),
            "images": entries,
            "stats": {
                "downloaded": enricher._downloaded,
                "reused": enricher._reused,
                "skipped": enricher._skipped,
            },
        }
        return {"data_model": enriched_model, "registry": registry}


def _load_json(path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[IMAGE-ENRICH] Could not read {path}: {e}")
        return None


def _extract_page_context(figma_data: Optional[Dict[str, Any]], spec_path: Optional[str]) -> str:
    if spec_path and Path(spec_path).exists():
        text = Path(spec_path).read_text(encoding="utf-8")
        match = re.search(r"^#\s+(.+)", text, re.MULTILINE)
        if match:
            return match.group(1).strip()
    if figma_data and figma_data.get("name"):
        return str(figma_data.get("name"))
    return ""


def _build_provider(provider_name: str, api_key: Optional[str]) -> ImageProvider:
    if provider_name == "unsplash":
        key = api_key or os.environ.get("UNSPLASH_ACCESS_KEY")
        if not key:
            raise ValueError("Unsplash provider requires --image-provider-api-key or UNSPLASH_ACCESS_KEY")
        return UnsplashProvider(access_key=key)
    if provider_name == "pollinations":
        return PollinationsProvider()
    if provider_name == "mock":
        return MockImageProvider()
    raise ValueError(f"Unknown image provider: {provider_name}")


def run_enrichment(
    data_model_file: str,
    figma_file: Optional[str] = None,
    asset_registry_file: Optional[str] = None,
    spec_file: Optional[str] = None,
    output_file: Optional[str] = None,
    registry_file: Optional[str] = None,
    provider_name: str = DEFAULT_PROVIDER,
    provider_api_key: Optional[str] = None,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    max_images: int = DEFAULT_MAX_IMAGES,
    skip_existing: bool = True,
) -> Dict[str, Any]:
    data_model = _load_json(data_model_file)
    if not data_model:
        raise FileNotFoundError(f"Data model file not found: {data_model_file}")

    figma_data = _load_json(figma_file) if figma_file else None
    asset_registry = _load_json(asset_registry_file) if asset_registry_file else None
    page_context = _extract_page_context(figma_data, spec_file)

    provider = _build_provider(provider_name, provider_api_key)
    pipeline = ImageEnrichmentPipeline(
        provider=provider,
        output_dir=output_dir,
        max_images=max_images,
        skip_existing=skip_existing,
    )
    result = pipeline.run(
        data_model,
        figma_data=figma_data,
        asset_registry=asset_registry,
        page_context=page_context,
    )

    out_path = Path(output_file) if output_file else Path("data_model.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result["data_model"], ensure_ascii=False, indent=2), encoding="utf-8")

    reg_path = Path(registry_file) if registry_file else Path(DEFAULT_REGISTRY_FILE)
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.write_text(json.dumps(result["registry"], ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[IMAGE-ENRICH] enriched {result['registry']['stats']['downloaded']} images, reused {result['registry']['stats']['reused']}")
    print(f"[IMAGE-ENRICH] data_model -> {out_path}")
    print(f"[IMAGE-ENRICH] registry -> {reg_path}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Image enrichment for Figma card data models")
    parser.add_argument("--data-model", default="data_model.json", help="Path to data_model.json")
    parser.add_argument("--figma-file", default="figma_node.json", help="Path to Figma node JSON")
    parser.add_argument("--asset-registry", default="public/asset_registry.json", help="Path to asset_registry.json")
    parser.add_argument("--spec-file", default="spec.md", help="Path to technical assignment/spec for context")
    parser.add_argument("--output", default="data_model.json", help="Output path for enriched data_model.json")
    parser.add_argument("--registry-output", default=DEFAULT_REGISTRY_FILE, help="Output path for enrichment registry")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, choices=["unsplash", "pollinations", "mock"], help="External image provider (pollinations does not require an API key)")
    parser.add_argument("--provider-api-key", default=os.environ.get("UNSPLASH_ACCESS_KEY"), help="API key for the provider")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory to save downloaded images")
    parser.add_argument("--max-images", type=int, default=DEFAULT_MAX_IMAGES, help="Maximum external images to download")
    parser.add_argument("--no-skip-existing", action="store_true", help="Re-download even if local file exists")
    args = parser.parse_args()

    run_enrichment(
        data_model_file=args.data_model,
        figma_file=args.figma_file,
        asset_registry_file=args.asset_registry,
        spec_file=args.spec_file,
        output_file=args.output,
        registry_file=args.registry_output,
        provider_name=args.provider,
        provider_api_key=args.provider_api_key,
        output_dir=args.output_dir,
        max_images=args.max_images,
        skip_existing=not args.no_skip_existing,
    )


if __name__ == "__main__":
    main()
