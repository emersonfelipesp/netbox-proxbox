"""Pydantic V2 schemas for service reachability check results."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from netbox_proxbox.schemas._base import ProxboxBaseModel

StatusLiteral = Literal["success", "error", "unknown"]
AuthStatusLiteral = Literal["success", "error", "pending"]


class FastAPIStatusResult(ProxboxBaseModel):
    """Return value from ``ServiceStatus.fastapi_status(pk)``."""

    url: str | None = None
    connected: bool = False
    connected_verify_ssl: bool = True
    target_address: str | None = None
    target_port: int | None = None
    authentication: AuthStatusLiteral = "error"
    api_access: AuthStatusLiteral = "error"
    detail: str | None = None
    http_status: int | None = None


class ServiceCheckResult(ProxboxBaseModel):
    """Return value from ``ServiceStatus.netbox_status()`` / ``proxmox_status()``."""

    target_address: str | None = None
    target_port: int | None = None
    authentication: AuthStatusLiteral = "error"
    api_access: AuthStatusLiteral = "error"
    detail: str | None = None
    http_status: int | None = None


class KeepalivePayload(ProxboxBaseModel):
    """JSON response body for ``GetServiceStatusView``."""

    status: StatusLiteral = "unknown"
    target_address: str | None = None
    target_port: int | None = None
    authentication: AuthStatusLiteral | None = None
    api_access: AuthStatusLiteral | None = None
    detail: str | None = None
    http_status: int | None = None
