"""Individual sync views for calling proxbox-api individual sync endpoints."""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _

__all__ = (
    "ProxmoxClusterSyncNowView",
    "ProxmoxNodeSyncNowView",
    "ProxmoxStorageSyncNowView",
    "VMBackupSyncNowView",
    "VMSnapshotSyncNowView",
    "VMTaskHistorySyncNowView",
    "VirtualMachineSyncNowView",
)


def __getattr__(name: str) -> type:
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
    if name == "VMBackupSyncNowView":
        from netbox_proxbox.views.sync_now.backup import VMBackupSyncNowView

        return VMBackupSyncNowView
    if name == "VMSnapshotSyncNowView":
        from netbox_proxbox.views.sync_now.snapshot import VMSnapshotSyncNowView

        return VMSnapshotSyncNowView
    if name == "VMTaskHistorySyncNowView":
        from netbox_proxbox.views.sync_now.task_history import VMTaskHistorySyncNowView

        return VMTaskHistorySyncNowView
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
    error = response.get("error") if isinstance(response, dict) else None
    if error:
        messages.error(request, _(f"Failed to sync {object_label.lower()}: {error}"))
    elif status == 200:
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
        messages.error(
            request,
            _(f"Failed to sync {object_label.lower()}: Unknown error"),
        )
    return HttpResponseRedirect(redirect_url)
