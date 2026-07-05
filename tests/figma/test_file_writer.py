"""Unit tests for figma-agent-core/file_writer.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
FILE_WRITER_PATH = ROOT / "figma-agent-core" / "file_writer.py"


def _load_file_writer() -> Any:
    spec = importlib.util.spec_from_file_location("figma_file_writer", str(FILE_WRITER_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_file_writer"] = module
    spec.loader.exec_module(module)
    return module


file_writer = _load_file_writer()


def test_sanitize_component_name_accepts_pascal_case() -> None:
    assert file_writer._sanitize_component_name("HeroSection") == "HeroSection"
    assert file_writer._sanitize_component_name("HeroSection.tsx") == "HeroSection"


def test_sanitize_component_name_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        file_writer._sanitize_component_name("")
    with pytest.raises(ValueError):
        file_writer._sanitize_component_name("123Bad")
    with pytest.raises(ValueError):
        file_writer._sanitize_component_name("hero-section")


def test_validate_target_dir_allows_inside_root(tmp_path: Path) -> None:
    target = tmp_path / "components"
    result = file_writer._validate_target_dir(str(target), str(tmp_path))
    assert result == target.resolve()


def test_validate_target_dir_rejects_outside_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Path traversal"):
        file_writer._validate_target_dir(str(tmp_path.parent / "outside"), str(tmp_path))


def test_write_component_creates_file(tmp_path: Path) -> None:
    result = file_writer.write_component(
        "HeroSection",
        "export default function HeroSection() { return <div />; }",
        target_dir=str(tmp_path / "components"),
        root_dir=str(tmp_path),
    )
    assert result.startswith("SUCCESS")
    assert (tmp_path / "components" / "HeroSection.tsx").exists()


def test_write_component_returns_error_for_invalid_name(tmp_path: Path) -> None:
    result = file_writer.write_component(
        "bad-name",
        "code",
        target_dir=str(tmp_path / "components"),
        root_dir=str(tmp_path),
    )
    assert result.startswith("ERROR")
