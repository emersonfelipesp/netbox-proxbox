"""Structural protocols shared across ProxBox plugin modules."""

from __future__ import annotations

from typing import Protocol


class FastAPIUrlSource(Protocol):
    """Structural type for models/objects passed to URL-building helpers."""

    ip_address: object | None
    domain: str | None
    websocket_domain: str | None
    verify_ssl: bool
    port: int
    websocket_port: int


class FastAPIAuthSource(Protocol):
    """Structural type for backend Bearer token resolution."""

    token: str
