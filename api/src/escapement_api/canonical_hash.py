from __future__ import annotations

from typing import Any

from escapement_engine.canonical import hash_value


def config_hash(config: dict[str, Any]) -> str:
    """Hash of an agent configuration: the reference cache key's middle part."""
    return hash_value({k: v for k, v in config.items() if not isinstance(v, float)})
