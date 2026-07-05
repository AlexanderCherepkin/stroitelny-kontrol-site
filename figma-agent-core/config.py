import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


_FIGMA_FILE_KEY_RE = re.compile(r"/(?:file|design)/([^/?#]+)")
_FIGMA_NODE_ID_RE = re.compile(r"[?&]node-id=([^&]+)")


_DOTENV_LOADED = False


def _ensure_dotenv() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        load_dotenv(str(env_path))
    else:
        load_dotenv()
    _DOTENV_LOADED = True


@dataclass(frozen=True)
class FigmaConfig:
    token: str
    file_key: str
    node_id: Optional[str]
    llm_api_key: str
    llm_api_url: str
    llm_model: str
    mcp_port: int


def _resolve_file_key(file_key: Optional[str], url: Optional[str]) -> Optional[str]:
    if file_key:
        return file_key.strip()
    if url:
        match = _FIGMA_FILE_KEY_RE.search(url)
        if match:
            return match.group(1)
    return None


def _resolve_node_id(node_id: Optional[str], url: Optional[str]) -> Optional[str]:
    if node_id:
        return node_id.strip().replace("-", ":")
    if url:
        match = _FIGMA_NODE_ID_RE.search(url)
        if match:
            return match.group(1).replace("-", ":")
    return None


def load_figma_config(env: Optional[dict] = None) -> FigmaConfig:
    if env is None:
        _ensure_dotenv()
        env = os.environ
    token = env.get("FIGMA_TOKEN", "").strip()
    file_key = _resolve_file_key(
        env.get("FIGMA_FILE_KEY", "").strip() or None,
        env.get("FIGMA_URL", "").strip() or None,
    )
    node_id = _resolve_node_id(
        env.get("FIGMA_NODE_ID", "").strip() or None,
        env.get("FIGMA_URL", "").strip() or None,
    )

    llm_api_key = env.get("LLM_API_KEY", env.get("ANTHROPIC_API_KEY", "")).strip()
    llm_api_url = env.get("LLM_API_URL", "").strip()
    llm_model = env.get("LLM_MODEL", "").strip()

    raw_port = env.get("MCP_PORT", "8080").strip()
    try:
        mcp_port = int(raw_port)
    except ValueError:
        mcp_port = 8080

    return FigmaConfig(
        token=token,
        file_key=file_key or "",
        node_id=node_id,
        llm_api_key=llm_api_key,
        llm_api_url=llm_api_url,
        llm_model=llm_model,
        mcp_port=mcp_port,
    )


def is_figma_configured(config: Optional[dict] = None) -> bool:
    cfg = load_figma_config(config)
    return bool(cfg.token and cfg.file_key)


def require_figma_config(config: Optional[dict] = None) -> FigmaConfig:
    cfg = load_figma_config(config)
    if not cfg.token:
        raise RuntimeError("FIGMA_TOKEN is required. Set it in .env or environment.")
    if not cfg.file_key:
        raise RuntimeError(
            "FIGMA_FILE_KEY (or FIGMA_URL containing a file key) is required."
        )
    return cfg
