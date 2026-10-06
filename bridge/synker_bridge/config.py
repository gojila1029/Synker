"""Small non-secret local config: which vault folder and Synker environment
this bridge instance is pointed at. Tokens never live here — see
token_store.py for those.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class BridgeConfig:
    vault_path: str
    environment: str


def default_config_path() -> Path:
    return Path.home() / ".synker-bridge" / "config.json"


def save_config(config: BridgeConfig, path: Path | None = None) -> None:
    target = path or default_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    os.replace(tmp, target)
    try:
        os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)  # 0600; best-effort on Windows
    except OSError:
        pass


def load_config(path: Path | None = None) -> BridgeConfig | None:
    target = path or default_config_path()
    if not target.exists():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return BridgeConfig(**data)
    except (json.JSONDecodeError, TypeError, OSError):
        return None
