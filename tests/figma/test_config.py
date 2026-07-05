"""Unit tests for figma-agent-core/config.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = ROOT / "figma-agent-core" / "config.py"


def _load_config() -> Any:
    spec = importlib.util.spec_from_file_location("figma_config", str(CONFIG_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_config"] = module
    spec.loader.exec_module(module)
    return module


config = _load_config()


def test_resolve_file_key_from_url() -> None:
    url = "https://www.figma.com/file/ABC123/My-Design?node-id=123%3A456"
    assert config._resolve_file_key(None, url) == "ABC123"


def test_resolve_file_key_explicit() -> None:
    assert config._resolve_file_key("XYZ789", None) == "XYZ789"


def test_resolve_node_id_from_url() -> None:
    url = "https://www.figma.com/file/ABC123/My-Design?node-id=123-456"
    assert config._resolve_node_id(None, url) == "123:456"


def test_resolve_node_id_explicit() -> None:
    assert config._resolve_node_id("789-012", None) == "789:012"


def test_load_figma_config_from_dict() -> None:
    env = {
        "FIGMA_TOKEN": "token-123",
        "FIGMA_FILE_KEY": "file-abc",
        "FIGMA_NODE_ID": "1:2",
        "LLM_API_KEY": "llm-key",
        "LLM_API_URL": "https://api.example.com",
        "LLM_MODEL": "claude-opus",
        "MCP_PORT": "9000",
    }
    cfg = config.load_figma_config(env)
    assert cfg.token == "token-123"
    assert cfg.file_key == "file-abc"
    assert cfg.node_id == "1:2"
    assert cfg.llm_api_key == "llm-key"
    assert cfg.llm_api_url == "https://api.example.com"
    assert cfg.llm_model == "claude-opus"
    assert cfg.mcp_port == 9000


def test_load_figma_config_fallback_port() -> None:
    cfg = config.load_figma_config({"MCP_PORT": "not-a-number"})
    assert cfg.mcp_port == 8080


def test_is_figma_configured_requires_token_and_file_key() -> None:
    assert config.is_figma_configured({"FIGMA_TOKEN": "t", "FIGMA_FILE_KEY": "f"})
    assert not config.is_figma_configured({"FIGMA_TOKEN": "t"})
    assert not config.is_figma_configured({"FIGMA_FILE_KEY": "f"})


def test_require_figma_config_raises_when_missing() -> None:
    with pytest.raises(RuntimeError, match="FIGMA_TOKEN"):
        config.require_figma_config({})
