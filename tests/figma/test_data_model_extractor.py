"""Unit tests for figma-agent-core/data_model_extractor.py.

Loads the module via importlib because the directory name contains a hyphen.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_MODEL_PATH = ROOT / "figma-agent-core" / "data_model_extractor.py"


def _load_data_model() -> Any:
    spec = importlib.util.spec_from_file_location("figma_data_model_extractor", str(DATA_MODEL_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_data_model_extractor"] = module
    spec.loader.exec_module(module)
    return module


data_model_extractor = _load_data_model()


def _card(name: str, title: str) -> dict[str, Any]:
    return {
        "id": f"{name}-id",
        "name": name,
        "type": "FRAME",
        "visible": True,
        "children": [
            {
                "id": f"{name}-title",
                "name": "Title",
                "type": "TEXT",
                "visible": True,
                "characters": title,
            },
            {
                "id": f"{name}-cover",
                "name": "Cover",
                "type": "IMAGE",
                "visible": True,
            },
        ],
    }


def test_module_loads() -> None:
    assert hasattr(data_model_extractor, "DataModelExtractor")
    assert hasattr(data_model_extractor, "extract_data_models")


def test_detects_repeated_card_structures() -> None:
    root = {
        "id": "page",
        "name": "Page",
        "type": "FRAME",
        "visible": True,
        "children": [
            _card("Card 1", "First card"),
            _card("Card 2", "Second card"),
            _card("Card 3", "Third card"),
        ],
    }
    extractor = data_model_extractor.DataModelExtractor(min_occurrences=2, top_n=10)
    report = extractor.extract(root)
    assert report["version"] == "1"
    assert len(report["models"]) == 1
    model = report["models"][0]
    assert model["name"] == "Card"
    assert model["occurrences"] == 3
    assert model["confidence"] > 0
    fields = {f["name"]: f["type"] for f in model["fields"]}
    assert "title" in fields
    assert "imageUrl" in fields
    assert fields["title"] == "String"
    assert fields["imageUrl"] == "String"
    assert model["sample_values"]["title"] == "First card"
    assert "Card" in model["suggested_prisma"]
    assert "@id" in model["suggested_prisma"]
    assert "id String @id @default(uuid())" in model["suggested_prisma"]
    assert model["sample_figma_id"] == "Card 1-id"
    assert "Card 1-id" in model["occurrence_ids"]


def test_respects_min_occurrences() -> None:
    root = {
        "id": "page",
        "name": "Page",
        "type": "FRAME",
        "visible": True,
        "children": [_card("Card 1", "Only card")],
    }
    extractor = data_model_extractor.DataModelExtractor(min_occurrences=2, top_n=10)
    report = extractor.extract(root)
    assert report["models"] == []


def test_top_n_limits_models() -> None:
    badges = [
        {
            "id": f"badge-{i}",
            "name": f"Badge {i}",
            "type": "FRAME",
            "visible": True,
            "children": [
                {
                    "id": f"badge-{i}-label",
                    "name": "Label",
                    "type": "TEXT",
                    "visible": True,
                    "characters": f"Badge {i}",
                }
            ],
        }
        for i in range(5)
    ]
    tags = [
        {
            "id": f"tag-{i}",
            "name": f"Tag {i}",
            "type": "FRAME",
            "visible": True,
            "children": [
                {
                    "id": f"tag-{i}-label",
                    "name": "Label",
                    "type": "TEXT",
                    "visible": True,
                    "characters": f"Tag {i}",
                }
            ],
        }
        for i in range(3)
    ]
    root = {
        "id": "page",
        "name": "Page",
        "type": "FRAME",
        "visible": True,
        "children": badges + tags,
    }
    extractor = data_model_extractor.DataModelExtractor(min_occurrences=2, top_n=1)
    report = extractor.extract(root)
    assert len(report["models"]) == 1
    assert report["models"][0]["name"] == "Badge"


def test_extract_data_models_writes_json(tmp_path: Path) -> None:
    figma_file = tmp_path / "figma_node.json"
    figma_file.write_text(
        json.dumps(
            {
                "id": "page",
                "name": "Page",
                "type": "FRAME",
                "visible": True,
                "children": [
                    _card("Card 1", "A"),
                    _card("Card 2", "B"),
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "data_model.json"
    report = data_model_extractor.extract_data_models(
        figma_file=str(figma_file),
        output=str(output),
        min_occurrences=2,
        top_n=10,
    )
    assert output.exists()
    assert report["version"] == "1"
    assert len(report["models"]) == 1
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded == report


def test_cli(tmp_path: Path) -> None:
    figma_file = tmp_path / "figma_node.json"
    figma_file.write_text(
        json.dumps(
            {
                "id": "page",
                "name": "Page",
                "type": "FRAME",
                "visible": True,
                "children": [
                    _card("Card 1", "A"),
                    _card("Card 2", "B"),
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "data_model.json"
    result = subprocess.run(
        [
            sys.executable,
            str(DATA_MODEL_PATH),
            "--file",
            str(figma_file),
            "--output",
            str(output),
            "--min-occurrences",
            "2",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert output.exists()
    assert "1 candidate model" in result.stdout

