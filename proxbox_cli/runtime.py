"""Config cache and client factory for the Proxbox CLI."""

from __future__ import annotations

from proxbox_cli.client import ProxboxApiClient
from proxbox_cli.config import Config, load_config

_CACHED_CONFIG: Config | None = None


def _ensure_config() -> Config:
    global _CACHED_CONFIG
    if _CACHED_CONFIG is None:
        _CACHED_CONFIG = load_config()
    return _CACHED_CONFIG


def _cache_config(cfg: Config) -> Config:
    global _CACHED_CONFIG
    _CACHED_CONFIG = cfg
    return cfg


def _get_client() -> ProxboxApiClient:
    return ProxboxApiClient(_ensure_config())
