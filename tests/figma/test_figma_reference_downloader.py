"""Unit tests for figma-agent-core/figma_reference_downloader.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
DOWNLOADER_PATH = ROOT / "figma-agent-core" / "figma_reference_downloader.py"


def _load_downloader() -> Any:
    spec = importlib.util.spec_from_file_location("figma_reference_downloader", str(DOWNLOADER_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_reference_downloader"] = module
    spec.loader.exec_module(module)
    return module


downloader = _load_downloader()


def test_parse_file_key_from_url() -> None:
    assert downloader._parse_file_key("https://www.figma.com/file/AbC123/X") == "AbC123"
    assert downloader._parse_file_key("https://www.figma.com/design/AbC123/X") == "AbC123"


def test_parse_file_key_plain() -> None:
    assert downloader._parse_file_key("AbC123") == "AbC123"
    assert downloader._parse_file_key("") is None


def test_download_writes_png(tmp_path: Path) -> None:
    output = tmp_path / "ref.png"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "err": None,
        "images": {"10:1": "https://example.com/image.png"},
    }
    mock_image = MagicMock()
    mock_image.status_code = 200
    mock_image.content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    with patch("requests.get", side_effect=[mock_response, mock_image]) as mock_get:
        result = downloader.download_figma_reference(
            node_id="10:1",
            output_path=str(output),
            token="test-token",
            file_key="AbC123",
            root_dir=str(tmp_path),
        )
        assert result["success"] is True
        assert result["path"] == str(output)
        assert output.exists()
        calls = [c.args[0] for c in mock_get.call_args_list]
        assert any("/v1/images/AbC123" in c for c in calls)


def test_download_reports_missing_token(tmp_path: Path) -> None:
    with patch.dict("os.environ", {}, clear=True):
        result = downloader.download_figma_reference(
            node_id="10:1",
            output_path=str(tmp_path / "ref.png"),
            token=None,
            file_key=None,
            root_dir=str(tmp_path),
        )
    assert result["success"] is False
    assert "figma" in result["error"].lower()


def test_download_outside_workspace_guard(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        downloader.download_figma_reference(
            node_id="10:1",
            output_path="/tmp/outside.png",
            token="t",
            file_key="k",
            root_dir=str(tmp_path),
        )
