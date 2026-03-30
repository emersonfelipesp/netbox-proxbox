"""NetBox-aligned permission helpers for ProxBox custom views."""

from core.models import Job
from utilities.permissions import get_permission_for_model

from netbox_proxbox.models import (
    FastAPIEndpoint,
    NetBoxEndpoint,
    ProxmoxEndpoint,
)

__all__ = (
    "permission_change_fastapi_endpoint",
    "permission_enqueue_proxbox_sync",
    "permission_view_fastapi_endpoint",
    "user_may_access_proxbox_dashboard",
)


def permission_change_fastapi_endpoint() -> str:
    """Required to manage FastAPI endpoint configuration (CRUD)."""
    return get_permission_for_model(FastAPIEndpoint, "change")


def permission_enqueue_proxbox_sync() -> str:
    """Required to enqueue Proxbox background sync jobs (including UI sync buttons)."""
    return get_permission_for_model(Job, "add")


def permission_view_fastapi_endpoint() -> str:
    """Required for read-only WebSocket / operational views tied to the backend."""
    return get_permission_for_model(FastAPIEndpoint, "view")


def user_may_access_proxbox_dashboard(user) -> bool:
    """True if the user may see any ProxBox endpoint inventory on the plugin home."""
    if not getattr(user, "is_authenticated", False):
        return False
    return any(
        (
            user.has_perm(get_permission_for_model(ProxmoxEndpoint, "view")),
            user.has_perm(get_permission_for_model(NetBoxEndpoint, "view")),
            user.has_perm(get_permission_for_model(FastAPIEndpoint, "view")),
        )
    )
