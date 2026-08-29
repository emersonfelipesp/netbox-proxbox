"""Local authorization and backend identity for template image build actions."""

from __future__ import annotations

from dataclasses import dataclass

from netbox_proxbox.services.backend_context import get_fastapi_request_context
from netbox_proxbox.views.backend_sync import resolve_backend_endpoint_id
from netbox_proxbox.views.proxbox_access import permission_run_proxmox_action


@dataclass(frozen=True, slots=True)
class TemplateBuildAuthorizationError(Exception):
    """Stable HTTP-safe denial raised before a template build is dispatched."""

    detail: str
    status_code: int


def require_template_build_authorization(user: object, endpoint: object) -> None:
    """Require operator permission plus enabled, broad, and narrow endpoint gates."""
    has_perm = getattr(user, "has_perm", None)
    if not callable(has_perm) or not has_perm(permission_run_proxmox_action()):
        raise TemplateBuildAuthorizationError(
            "Missing core.run_proxmox_action permission.", 403
        )
    if not bool(getattr(endpoint, "enabled", False)):
        raise TemplateBuildAuthorizationError(
            "Endpoint is disabled; template image builds are not authorized.", 403
        )
    if not bool(getattr(endpoint, "allow_writes", False)):
        raise TemplateBuildAuthorizationError(
            "Endpoint does not allow Proxmox-side writes.", 403
        )
    if not bool(getattr(endpoint, "allow_packer_template_builds", False)):
        raise TemplateBuildAuthorizationError(
            "Endpoint does not explicitly allow netbox-packer template builds.", 403
        )


def resolve_authorized_backend_endpoint_id(endpoint: object) -> int:
    """Translate the authorized NetBox endpoint to proxbox-api's database id."""
    context = get_fastapi_request_context()
    if context is None or not context.http_url:
        raise TemplateBuildAuthorizationError(
            "No enabled ProxBox (FastAPI) backend is configured.", 503
        )

    backend_endpoint_id, resolve_error = resolve_backend_endpoint_id(
        endpoint,
        base_url=context.http_url.rstrip("/"),
        auth_headers=context.headers or {},
        backend_verify_ssl=bool(context.verify_ssl),
    )
    if backend_endpoint_id is None:
        raise TemplateBuildAuthorizationError(
            resolve_error or "Could not resolve this endpoint on the ProxBox backend.",
            503,
        )
    return backend_endpoint_id
