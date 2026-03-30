"""Structured types and protocols shared across ProxBox plugin modules."""

from __future__ import annotations

from typing import Any, Protocol, TypedDict


class FastAPIUrlDict(TypedDict):
    """Resolved HTTP/WebSocket URLs and TLS flag for a FastAPI (ProxBox backend) endpoint."""

    domain: Any
    ip_address: Any
    ip_address_url: str
    http_url: str
    websocket_url: str
    verify_ssl: bool


class BackendRequestContext(TypedDict, total=False):
    """Parameters needed to call the ProxBox FastAPI backend over HTTP."""

    detail: dict[str, Any]
    http_url: str | None
    ip_address_url: str | None
    verify_ssl: bool
    headers: dict[str, str]


class FastAPIUrlSource(Protocol):
    """Structural type for models/objects passed to URL-building helpers."""

    ip_address: Any
    domain: Any
    websocket_domain: Any
    verify_ssl: bool
    port: int
    websocket_port: int


class FastAPIAuthSource(Protocol):
    """Structural type for backend Bearer token resolution."""

    token: str
