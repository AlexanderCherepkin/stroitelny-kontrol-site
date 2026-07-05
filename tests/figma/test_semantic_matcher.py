"""Unit tests for semantic matching layer used by Design System Intelligence."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SEMANTIC_MATCHER_PATH = ROOT / "figma-agent-core" / "semantic_matcher.py"


def _load_semantic_matcher() -> Any:
    spec = importlib.util.spec_from_file_location("figma_semantic_matcher", str(SEMANTIC_MATCHER_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_semantic_matcher"] = module
    spec.loader.exec_module(module)
    return module


matcher_module = _load_semantic_matcher()


def test_tokenize_and_normalize() -> None:
    assert matcher_module._normalize_text("Primary / Button!") == "primary button"
    assert matcher_module._tokenize("Primary Button") == ["primary", "button"]


def test_jaccard_zero_for_empty() -> None:
    assert matcher_module._jaccard(set(), set()) == 0.0


def test_levenshtein_ratio_identical() -> None:
    assert matcher_module._levenshtein_ratio("button", "button") == 1.0


def test_semantic_score_exact_match() -> None:
    score, _ = matcher_module._semantic_score({"name": "Button"}, {"name": "Button"})
    assert score == 1.0


def test_semantic_score_no_overlap() -> None:
    score, _ = matcher_module._semantic_score({"name": "Button"}, {"name": "Carousel"})
    assert 0.0 <= score < 0.4


def test_semantic_index_matches_component_by_name() -> None:
    registry = {
        "local_components": {
            "Button": {
                "export_name": "Button",
                "file_path": "src/components/ui/Button.tsx",
                "props": {"variant": "string", "size": "string"},
            }
        }
    }
    index = matcher_module.SemanticIndex.from_component_registry(registry)
    figma_entry = {
        "name": "Primary Button",
        "pascal_name": "Button",
        "variant_properties": {"Variant": {"values": ["Primary", "Secondary"]}},
    }
    match, score, reason = index.match_component(figma_entry, threshold=0.5)
    assert match is not None
    assert match["entry"]["export_name"] == "Button"
    assert score >= 0.5
    assert "name" in reason


def test_semantic_index_respects_threshold() -> None:
    registry = {
        "local_components": {
            "Card": {
                "export_name": "Card",
                "file_path": "src/components/ui/Card.tsx",
                "props": {},
            }
        }
    }
    index = matcher_module.SemanticIndex.from_component_registry(registry)
    figma_entry = {"name": "HeroSection", "pascal_name": "HeroSection", "variant_properties": {}}
    match, score, _ = index.match_component(figma_entry, threshold=0.8)
    assert match is None


def test_semantic_index_matches_token_by_description() -> None:
    registry = {
        "colors": {
            "primary": {
                "hex": "#3b82f5",
                "description": "Main brand color used for primary actions",
                "contexts": ["button", "cta"],
            }
        }
    }
    index = matcher_module.SemanticIndex.from_token_registry(registry)
    key, score, reason = index.match_token(
        {"name": "colors/primary/500", "description": "Primary action color", "contexts": "button"},
        threshold=0.4,
    )
    assert key == "primary"
    assert score >= 0.4


def test_semantic_matcher_find_local_component_returns_candidate() -> None:
    registry = {
        "local_components": {
            "SubmitButton": {
                "export_name": "SubmitButton",
                "file_path": "src/components/ui/SubmitButton.tsx",
                "props": {},
            }
        }
    }
    index = matcher_module.SemanticIndex.from_component_registry(registry)
    matcher = matcher_module.SemanticMatcher(index, threshold=0.5)
    match, score, reason = matcher.find_local_component({"name": "Submit", "pascal_name": "Submit", "variant_properties": {}})
    assert match is not None
    assert match["entry"]["export_name"] == "SubmitButton"
    assert score >= 0.5


def test_save_and_load_index(tmp_path: Path) -> None:
    registry = {
        "local_components": {
            "Button": {
                "export_name": "Button",
                "file_path": "src/components/ui/Button.tsx",
                "props": {},
            }
        }
    }
    index = matcher_module.SemanticIndex.from_component_registry(registry)
    path = tmp_path / "index.json"
    index.save(path)
    loaded = matcher_module.SemanticIndex.load(path)
    assert len(loaded.components) == 1
    assert loaded.components[0]["key"] == "Button"


def test_semantic_index_matches_component_by_jsdoc_description() -> None:
    registry = {
        "local_components": {
            "ActionButton": {
                "export_name": "ActionButton",
                "file_path": "src/components/ui/ActionButton.tsx",
                "description": "Primary call-to-action button for forms and dialogs",
                "doc": "Primary call-to-action button for forms and dialogs",
                "tags": ["@tag action cta primary"],
                "props": {"variant": "string", "size": "string"},
            }
        }
    }
    index = matcher_module.SemanticIndex.from_component_registry(registry)
    figma_entry = {
        "name": "Action Button",
        "pascal_name": "ActionButton",
        "description": "Main call-to-action button for forms",
        "variant_properties": {},
    }
    match, score, reason = index.match_component(figma_entry, threshold=0.4)
    assert match is not None
    assert match["entry"]["export_name"] == "ActionButton"
    assert score >= 0.4
    # Description/doc field must contribute to the reason or the overall match.
    assert "description" in reason or "doc" in reason or "name" in reason
