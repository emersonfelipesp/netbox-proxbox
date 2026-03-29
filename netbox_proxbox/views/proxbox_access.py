"""NetBox-aligned permission helpers for ProxBox custom views."""

from utilities.permissions import get_permission_for_model

from netbox_proxbox.models import (
    FastAPIEndpoint,
    NetBoxEndpoint,
    ProxmoxEndpoint,
    SyncProcess,
)

__all__ = (
    "permission_change_fastapi_endpoint",
    "permission_add_sync_process",
    "permission_view_fastapi_endpoint",
    "user_may_access_proxbox_dashboard",
)


def permission_change_fastapi_endpoint() -> str:
    """Required to trigger sync against the ProxBox FastAPI backend."""
    return get_permission_for_model(FastAPIEndpoint, "change")


def permission_add_sync_process() -> str:
    """Required to enqueue a ProxBox background sync job."""
    return get_permission_for_model(SyncProcess, "add")


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
