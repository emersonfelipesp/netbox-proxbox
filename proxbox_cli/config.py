"""Configuration model and persistence for the Proxbox CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel

DEFAULT_CONFIG_DIR = "proxbox-cli"
DEFAULT_CONFIG_FILENAME = "config.json"
DEFAULT_BASE_URL = "http://localhost:8000"
BASE_URL_ENV_VAR = "PROXBOX_URL"
NETBOX_PATH_ENV_VAR = "NETBOX_PATH"


class Config(BaseModel):
    """Config implementation."""

    base_url: str = DEFAULT_BASE_URL
    timeout: float = 30.0
    netbox_manage_py: str | None = None


def config_dir() -> Path:
    """Handle config dir."""
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    base = Path(xdg).expanduser() if xdg else Path("~/.config").expanduser()
    return base / DEFAULT_CONFIG_DIR


def config_path() -> Path:
    """Handle config path."""
    return config_dir() / DEFAULT_CONFIG_FILENAME


def normalize_base_url(raw: str) -> str:
    """Strip trailing slashes; auto-prefix http:// if no scheme is present."""
    raw = raw.strip().rstrip("/")
    if raw and "://" not in raw:
        raw = f"http://{raw}"
    return raw


def load_config() -> Config:
    """Load config from disk, falling back to env var, then defaults."""
    path = config_path()
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Environment variable overrides the file value.
    env_url = os.environ.get(BASE_URL_ENV_VAR, "").strip()
    if env_url:
        data["base_url"] = normalize_base_url(env_url)

    return Config(**data)


def save_config(cfg: Config) -> None:
    """Persist config to disk with restricted permissions."""
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    p = config_path()
    p.write_text(json.dumps(cfg.model_dump(), indent=2))
    os.chmod(p, 0o600)
