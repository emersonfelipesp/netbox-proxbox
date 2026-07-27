"""Structural protocols shared across ProxBox plugin modules."""

from __future__ import annotations

from typing import Protocol


class FastAPIUrlSource(Protocol):
    """Structural type for models/objects passed to URL-building helpers."""

    pk: object | None
    enabled: bool
    ip_address: object | None
    domain: str | None
    port: int
    use_https: bool
    verify_ssl: bool
    use_websocket: bool
    websocket_domain: str | None
    websocket_port: int | None
    server_side_websocket: bool
    backend_key_target_fingerprint: str


class FastAPIAuthSource(FastAPIUrlSource, Protocol):
    """Structural type for backend Bearer token resolution."""

    token: str
