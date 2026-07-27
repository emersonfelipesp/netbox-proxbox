"""Lazy service-layer exports for backend proxy and keepalive helpers.

Keeping this package initializer import-light lets pure URL/auth helpers import
security submodules without bootstrapping Django models. Public compatibility
exports are resolved on first access.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_BACKEND_PROXY_EXPORTS = frozenset(
    {
        "get_backend_bootstrap_status",
        "get_fastapi_request_context",
        "iter_backend_sse_lines",
        "reconcile_backend_custom_fields",
        "run_sync_stream",
        "sse_error_frames",
        "sync_full_update_resource",
        "sync_resource",
    }
)

__all__ = (
    "ServiceStatus",
    "get_backend_bootstrap_status",
    "get_fastapi_request_context",
    "iter_backend_sse_lines",
    "reconcile_backend_custom_fields",
    "run_sync_stream",
    "sse_error_frames",
    "sync_full_update_resource",
    "sync_resource",
)


def __getattr__(name: str) -> Any:
    """Resolve compatibility exports without eager Django model imports."""
    if name == "ServiceStatus":
        from netbox_proxbox.services.service_status import ServiceStatus

        value: Any = ServiceStatus
    elif name in _BACKEND_PROXY_EXPORTS:
        backend_proxy = import_module("netbox_proxbox.services.backend_proxy")
        value = getattr(backend_proxy, name)
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value
    return value
