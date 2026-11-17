"""NetBox-aligned permission helpers for ProxBox custom views."""

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.mixins import AccessMixin
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse
from utilities.views import ContentTypePermissionRequiredMixin

from core.models import Job
from utilities.permissions import get_permission_for_model

from netbox_proxbox.utils.actor_header import header_safe_actor
from netbox_proxbox.operational_security import (
    LEGACY_PROXMOX_ACTION_PERMISSION,
    endpoint_action_is_authorized,
    request_token_allows_write,
    user_has_any_operational_permission,
)

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
    "EndpointOperationalPermissionRequiredMixin",
    "TokenWriteScopeRequiredMixin",
    "ENDPOINT_OPERATIONAL_ACTION",
    "permission_authorize_deletion_request",
    "actor_from_request",
    "permission_change_fastapi_endpoint",
    "permission_change_proxbox_plugin_settings",
    "permission_enqueue_proxbox_sync",
    "permission_intent_create_lxc",
    "permission_intent_create_vm",
    "permission_intent_delete_lxc",
    "permission_intent_delete_vm",
    "permission_intent_update_lxc",
    "permission_intent_update_vm",
    "permission_open_console",
    "permission_open_ssh_terminal",
    "permission_reset_encrypted_secrets",
    "permission_run_endpoint_action",
    "permission_run_proxmox_action",
    "request_token_allows_write",
    "user_can_run_endpoint_action",
    "user_has_any_endpoint_action",
    "permission_view_fastapi_endpoint",
    "user_may_access_proxbox_dashboard",
)

PROXMOX_ACTION_PERMISSION = LEGACY_PROXMOX_ACTION_PERMISSION
ENDPOINT_OPERATIONAL_ACTION = "run_proxmox_action"
SSH_TERMINAL_ACTION = "open_ssh_terminal"
CONSOLE_ACTION = "open_console"
TOKEN_WRITE_REQUIRED_MESSAGE = "API token does not allow write operations."


def actor_from_request(request: HttpRequest) -> str:
    """Return the authenticated actor name used by proxbox-api write routes."""
    user = getattr(request, "user", None)
    get_username = getattr(user, "get_username", None)
    if callable(get_username):
        return header_safe_actor(str(get_username()))
    return header_safe_actor(
        str(getattr(user, "username", "") or getattr(user, "pk", "") or "netbox")
    )


class TokenWriteScopeRequiredMixin:
    """Reject unsafe requests authenticated by a read-only API token."""

    def dispatch(
        self, request: HttpRequest, *args: object, **kwargs: object
    ) -> HttpResponse:
        if request.method not in {
            "GET",
            "HEAD",
            "OPTIONS",
        } and not request_token_allows_write(request):
            return HttpResponse(TOKEN_WRITE_REQUIRED_MESSAGE, status=403)
        return super().dispatch(request, *args, **kwargs)


def user_has_any_endpoint_action(user: object) -> bool:
    """Return whether the actor has a current or deprecated operational grant."""
    return user_has_any_operational_permission(
        user,
        permission_run_endpoint_action(),
    )


def user_can_run_endpoint_action(user: object, endpoint_id: object) -> bool:
    """Authorize one endpoint through object scope or the deprecated legacy grant."""
    return endpoint_action_is_authorized(
        user,
        endpoint_id,
        endpoint_objects=ProxmoxEndpoint.objects,
        endpoint_action=ENDPOINT_OPERATIONAL_ACTION,
    )


class EndpointOperationalPermissionRequiredMixin(ContentTypePermissionRequiredMixin):
    """Gate views on any grant, before their endpoint-specific scope check."""

    def get_required_permission(self) -> str:
        return permission_run_endpoint_action()

    def has_permission(self) -> bool:
        return user_has_any_endpoint_action(self.request.user)


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


def permission_reset_encrypted_secrets() -> str:
    """Required for the destructive encrypted-secret recovery workflow."""

    return get_permission_for_model(
        ProxboxPluginSettings,
        "reset_encrypted_secrets",
    )


def permission_enqueue_proxbox_sync() -> str:
    """Required to enqueue Proxbox background sync jobs (including UI sync buttons)."""
    return get_permission_for_model(Job, "add")


def permission_run_proxmox_action() -> str:
    """Return the deprecated literal operational permission compatibility name.

    New grants must use ``permission_run_endpoint_action()`` and exact endpoint
    scoping. Existing authentication backends that already yield this literal
    remain accepted additively during the compatibility transition.
    """
    return PROXMOX_ACTION_PERMISSION


def permission_run_endpoint_action() -> str:
    """Grantable, object-scoped operational permission on ``ProxmoxEndpoint``.

    NetBox renders object permissions as ``<app>.<action>_<model>``, so the
    literal ``core.run_proxmox_action`` cannot be granted to non-superusers
    through an ObjectPermission. This custom action on ``ProxmoxEndpoint``
    can be: add ``run_proxmox_action`` as an additional action on an object
    permission for Proxmox endpoints, optionally constrained to some of them.
    Endpoint-wide operations (HA arm/disarm) use it with
    ``ProxmoxEndpoint.objects.restrict(user, ENDPOINT_OPERATIONAL_ACTION)``.
    """
    return get_permission_for_model(ProxmoxEndpoint, ENDPOINT_OPERATIONAL_ACTION)


def permission_open_ssh_terminal() -> str:
    """Required to open browser SSH terminal sessions through proxbox-api."""
    return get_permission_for_model(ProxmoxEndpoint, SSH_TERMINAL_ACTION)


def permission_open_console() -> str:
    """Required to open a synchronized VM console through proxbox-api."""
    return get_permission_for_model(ProxmoxEndpoint, CONSOLE_ACTION)


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
