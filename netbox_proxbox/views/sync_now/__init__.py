"""Individual sync views for calling proxbox-api individual sync endpoints."""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _

__all__ = (
    "ProxmoxClusterSyncNowView",
    "ProxmoxNodeSyncNowView",
    "ProxmoxStorageSyncNowView",
    "VirtualMachineSyncNowView",
)


def __getattr__(name: str):
    """Lazy-load sync-now views to avoid circular imports during module init."""
    if name == "ProxmoxClusterSyncNowView":
        from netbox_proxbox.views.sync_now.cluster import ProxmoxClusterSyncNowView

        return ProxmoxClusterSyncNowView
    if name == "ProxmoxNodeSyncNowView":
        from netbox_proxbox.views.sync_now.node import ProxmoxNodeSyncNowView

        return ProxmoxNodeSyncNowView
    if name == "ProxmoxStorageSyncNowView":
        from netbox_proxbox.views.sync_now.storage import ProxmoxStorageSyncNowView

        return ProxmoxStorageSyncNowView
    if name == "VirtualMachineSyncNowView":
        from netbox_proxbox.views.sync_now.vm import VirtualMachineSyncNowView

        return VirtualMachineSyncNowView
    raise AttributeError(name)


def _handle_sync_response(
    request,
    response,
    status,
    dependencies,
    object_label,
    redirect_url,
) -> HttpResponseRedirect:
    """Translate a sync API response into user-facing messages and redirect."""
    if status == 200:
        action = response.get("action", "synced")
        messages.success(
            request,
            _(f"{object_label} {action} successfully.")
            + (f" ({len(dependencies)} dependencies synced)" if dependencies else ""),
        )
    elif status == 422:
        messages.error(
            request, _(f"Invalid parameters for {object_label.lower()} sync.")
        )
    elif status == 503:
        messages.error(
            request,
            _(f"Proxbox backend is unavailable for {object_label.lower()} sync."),
        )
    else:
        error = response.get("error", "Unknown error")
        messages.error(request, _(f"Failed to sync {object_label.lower()}: {error}"))
    return HttpResponseRedirect(redirect_url)
