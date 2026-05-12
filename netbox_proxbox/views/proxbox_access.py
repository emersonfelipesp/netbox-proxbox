"""NetBox-aligned permission helpers for ProxBox custom views."""

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.mixins import AccessMixin
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse

from core.models import Job
from utilities.permissions import get_permission_for_model

from netbox_proxbox.models import (
    FastAPIEndpoint,
    NetBoxEndpoint,
    ProxboxPluginSettings,
    ProxmoxEndpoint,
)

__all__ = (
    "RequireProxboxDashboardAccessMixin",
    "permission_change_fastapi_endpoint",
    "permission_change_proxbox_plugin_settings",
    "permission_enqueue_proxbox_sync",
    "permission_run_proxmox_action",
    "permission_view_fastapi_endpoint",
    "user_may_access_proxbox_dashboard",
)

PROXMOX_ACTION_PERMISSION = "core.run_proxmox_action"


class RequireProxboxDashboardAccessMixin(AccessMixin):
    """Require view permission on at least one endpoint model when authenticated."""

    def dispatch(
        self, request: HttpRequest, *args: object, **kwargs: object
    ) -> HttpResponse:
        """Block authenticated users who cannot see any ProxBox endpoint inventory."""
        if request.user.is_authenticated and not user_may_access_proxbox_dashboard(
            request.user
        ):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


def permission_change_fastapi_endpoint() -> str:
    """Required to manage FastAPI endpoint configuration (CRUD)."""
    return get_permission_for_model(FastAPIEndpoint, "change")


def permission_change_proxbox_plugin_settings() -> str:
    """Required to manage ProxBox plugin behavior settings."""
    return get_permission_for_model(ProxboxPluginSettings, "change")


def permission_enqueue_proxbox_sync() -> str:
    """Required to enqueue Proxbox background sync jobs (including UI sync buttons)."""
    return get_permission_for_model(Job, "add")


def permission_run_proxmox_action() -> str:
    """Required to dispatch operational verbs (start/stop/snapshot/migrate) via proxbox-api.

    Single permission gates all four verbs. Pair with ``ProxmoxEndpoint.allow_writes``
    on the target endpoint — both must be true for the verb to dispatch. See
    ``docs/design/operational-verbs.md`` for the full contract.
    """
    return PROXMOX_ACTION_PERMISSION


def permission_view_fastapi_endpoint() -> str:
    """Required for read-only WebSocket / operational views tied to the backend."""
    return get_permission_for_model(FastAPIEndpoint, "view")


def user_may_access_proxbox_dashboard(user: AbstractBaseUser | AnonymousUser) -> bool:
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
