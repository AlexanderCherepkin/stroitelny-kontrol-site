"""Unit tests for figma-agent-core/image_enrichment.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
ENRICHMENT_PATH = ROOT / "figma-agent-core" / "image_enrichment.py"


def _load_enrichment() -> Any:
    spec = importlib.util.spec_from_file_location("figma_image_enrichment", str(ENRICHMENT_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_image_enrichment"] = module
    spec.loader.exec_module(module)
    return module


enrichment = _load_enrichment()


def _make_data_model(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": "1",
        "models": [
            {
                "name": "FeatureCard",
                "occurrences": len(rows),
                "sample_figma_id": "1:1",
                "occurrence_ids": [f"occ{i}" for i in range(len(rows))],
                "fields": [{"name": "title", "type": "String"}, {"name": "imageUrl", "type": "String"}],
                "field_map": {"title": "title", "imageUrl": "imageUrl"},
                "sample_values": rows[0] if rows else {},
                "sample_data": rows,
                "confidence": 0.9,
                "suggested_prisma": "model FeatureCard { id String @id @default(uuid) title String imageUrl String }",
            }
        ],
    }


def test_enriches_empty_image_urls(tmp_path: Path) -> None:
    rows = [{"title": "Fast setup"}, {"title": "Secure by default"}]
    data_model = _make_data_model(rows)
    provider = enrichment.MockImageProvider()
    pipeline = enrichment.ImageEnrichmentPipeline(
        provider=provider,
        output_dir=str(tmp_path / "public" / "assets" / "enriched"),
    )
    result = pipeline.run(data_model, figma_data={"name": "SaaS Landing"})

    registry = result["registry"]
    assert registry["stats"]["downloaded"] == 2
    assert registry["stats"]["reused"] == 0

    enriched = result["data_model"]["models"][0]
    for row in enriched["sample_data"]:
        assert row["imageUrl"].startswith("/assets/enriched/")
        assert row["imageAlt"]
    assert "imageAlt" in enriched["field_map"]


def test_reuses_figma_asset_when_available(tmp_path: Path) -> None:
    rows = [{"title": "Card with real image"}]
    data_model = _make_data_model(rows)
    data_model["models"][0]["occurrence_ids"] = ["card:1"]

    figma_data = {
        "id": "page:1",
        "name": "Landing",
        "children": [
            {
                "id": "card:1",
                "type": "FRAME",
                "children": [
                    {"id": "img:1", "type": "IMAGE", "name": "Photo"},
                    {"id": "txt:1", "type": "TEXT", "characters": "Card with real image"},
                ],
            }
        ],
    }
    asset_registry = {
        "assets": {
            "img:1": {
                "publicPath": "/assets/figma/photo_img_1.png",
                "type": "raster",
                "format": "png",
                "width": 100,
                "height": 100,
            }
        }
    }
    provider = enrichment.MockImageProvider()
    pipeline = enrichment.ImageEnrichmentPipeline(
        provider=provider,
        output_dir=str(tmp_path / "public" / "assets" / "enriched"),
    )
    result = pipeline.run(data_model, figma_data=figma_data, asset_registry=asset_registry)

    registry = result["registry"]
    assert registry["stats"]["downloaded"] == 0
    assert registry["stats"]["reused"] == 1

    row = result["data_model"]["models"][0]["sample_data"][0]
    assert row["imageUrl"] == "/assets/figma/photo_img_1.png"


def test_respects_max_images(tmp_path: Path) -> None:
    rows = [{"title": f"Card {i}"} for i in range(5)]
    data_model = _make_data_model(rows)
    provider = enrichment.MockImageProvider()
    pipeline = enrichment.ImageEnrichmentPipeline(
        provider=provider,
        output_dir=str(tmp_path / "public" / "assets" / "enriched"),
        max_images=2,
    )
    result = pipeline.run(data_model, figma_data={"name": "Landing"})

    assert result["registry"]["stats"]["downloaded"] == 2
    filled = [r for r in result["data_model"]["models"][0]["sample_data"] if r.get("imageUrl")]
    assert len(filled) == 2


def test_run_enrichment_cli_writes_files(tmp_path: Path) -> None:
    rows = [{"title": "Hero image"}]
    data_model = _make_data_model(rows)
    data_model_path = tmp_path / "data_model.json"
    data_model_path.write_text(json.dumps(data_model), encoding="utf-8")

    figma_path = tmp_path / "figma_node.json"
    figma_path.write_text(json.dumps({"name": "Landing"}), encoding="utf-8")

    output_path = tmp_path / "data_model_out.json"
    registry_path = tmp_path / "registry.json"

    enrichment.run_enrichment(
        data_model_file=str(data_model_path),
        figma_file=str(figma_path),
        output_file=str(output_path),
        registry_file=str(registry_path),
        provider_name="mock",
        output_dir=str(tmp_path / "public" / "assets" / "enriched"),
    )

    assert output_path.exists()
    assert registry_path.exists()
    enriched = json.loads(output_path.read_text(encoding="utf-8"))
    assert enriched["models"][0]["sample_data"][0]["imageUrl"].startswith("/assets/enriched/")


def test_query_builder_uses_title_and_page_context() -> None:
    builder = enrichment.QueryBuilder(page_context="Modern team collaboration")
    query = builder.build_query({"title": "Fast setup", "description": "Deploy in minutes"}, "FeatureCard")
    assert "fast" in query
    assert "setup" in query
    assert "deploy" in query or "minutes" in query or "team" in query or "collaboration" in query
