"""NetBox-aligned permission helpers for ProxBox custom views."""

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.mixins import AccessMixin
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse

from core.models import Job
from utilities.permissions import get_permission_for_model

from netbox_proxbox.models import (
    DeletionRequest,
    FastAPIEndpoint,
    NetBoxEndpoint,
    ProxboxPluginSettings,
    ProxmoxApplyJob,
    ProxmoxEndpoint,
)

__all__ = (
    "RequireProxboxDashboardAccessMixin",
    "permission_authorize_deletion_request",
    "permission_change_fastapi_endpoint",
    "permission_change_proxbox_plugin_settings",
    "permission_enqueue_proxbox_sync",
    "permission_intent_create_lxc",
    "permission_intent_create_vm",
    "permission_intent_delete_lxc",
    "permission_intent_delete_vm",
    "permission_intent_update_lxc",
    "permission_intent_update_vm",
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


def _apply_job_intent_perm(codename: str) -> str:
    return f"{ProxmoxApplyJob._meta.app_label}.{codename}"


def permission_intent_create_vm() -> str:
    """Required to request a Proxmox QEMU VM CREATE via the intent merge path."""
    return _apply_job_intent_perm("intent_create_vm")


def permission_intent_update_vm() -> str:
    """Required to request a Proxmox QEMU VM UPDATE via the intent merge path."""
    return _apply_job_intent_perm("intent_update_vm")


def permission_intent_delete_vm() -> str:
    """Required to request a Proxmox QEMU VM DELETE via the intent merge path.

    Distinct from ``authorize_deletion_request``: this permission lets a user
    *request* a delete; the DeletionRequest still requires a separate user with
    ``authorize_deletion_request`` to approve it (four-eyes). The two are
    intentionally on different ContentTypes so they can be granted to different
    roles.
    """
    return _apply_job_intent_perm("intent_delete_vm")


def permission_intent_create_lxc() -> str:
    """Required to request a Proxmox LXC container CREATE via the intent merge path."""
    return _apply_job_intent_perm("intent_create_lxc")


def permission_intent_update_lxc() -> str:
    """Required to request a Proxmox LXC container UPDATE via the intent merge path."""
    return _apply_job_intent_perm("intent_update_lxc")


def permission_intent_delete_lxc() -> str:
    """Required to request a Proxmox LXC container DELETE via the intent merge path.

    Four-eyes pair of ``authorize_deletion_request`` — see
    ``permission_intent_delete_vm`` for the same rationale.
    """
    return _apply_job_intent_perm("intent_delete_lxc")


def permission_authorize_deletion_request() -> str:
    """Required to approve or reject a pending DeletionRequest (four-eyes).

    Held separately from ``intent_delete_*``; a single user holding both still
    cannot self-approve unless
    ``ProxboxPluginSettings.intent_apply_authorization_self_approve_allowed=True``
    (default ``False``).
    """
    return f"{DeletionRequest._meta.app_label}.authorize_deletion_request"


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
