"""Client configuration: environment first, then ~/.config/escapement/config.json."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "http://localhost:3000"


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / "escapement"


def load_config() -> dict[str, Any]:
    path = config_dir() / "config.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_config(**values: Any) -> Path:
    path = config_dir() / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_config()
    data.update({k: v for k, v in values.items() if v is not None})
    path.write_text(json.dumps(data, indent=2))
    path.chmod(0o600)
    return path


def resolve(api_key: str | None = None, base_url: str | None = None) -> tuple[str | None, str]:
    cfg = load_config()
    key = api_key or os.environ.get("ESCAPEMENT_API_KEY") or cfg.get("api_key")
    url = base_url or os.environ.get("ESCAPEMENT_BASE_URL") or cfg.get("base_url") or DEFAULT_BASE_URL
    return key, url.rstrip("/")
