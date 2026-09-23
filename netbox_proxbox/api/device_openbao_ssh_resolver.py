"""Resolve a linked device's SSH credential for the by-node secrets API.

Used only as a fallback when no local ``NodeSSHCredential`` row exists for a
``ProxmoxNode``. When the node is linked to a NetBox ``dcim.Device``, this
looks up a single credentialed SSH ``netbox_openbao.ServiceEndpoint`` for that
device and reveals its ``Credential`` through the same audited
``reveal_credential_material`` path used everywhere else in this integration.

netbox-openbao is optional: nothing here imports it at module load time, and
every lookup goes through ``django.apps.apps`` so the module degrades cleanly
when the companion is absent. It also degrades cleanly when netbox-openbao is
installed but predates the ``ServiceEndpoint``/``Credential`` models this
module expects — ``apps.get_model()`` raises ``LookupError`` for a model an
installed app doesn't define, and that is treated as "not available", the
same as netbox-openbao being uninstalled (see
docs/companion-plugins/netbox-openbao.md for the version this currently
affects). More than one credentialed SSH endpoint for a device is a
**denial** — callers may narrow the match with an explicit port — never a
reason to keep searching.

Nothing in this module logs credential material. Failures raise
``django.core.exceptions.PermissionDenied`` so the REST view can translate
them to a 403 without ever serializing the underlying provider error.
"""

from __future__ import annotations

import logging
from typing import Any

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied

logger = logging.getLogger("netbox_proxbox.api.device_openbao_ssh_resolver")

_SERVICE_TYPE_SSH = "ssh"
_CREDENTIAL_TYPE_SSH_KEYPAIR = "ssh-keypair"
_SSH_CREDENTIAL_TYPES = frozenset({"ssh-password", _CREDENTIAL_TYPE_SSH_KEYPAIR})


def _get_openbao_model(app_label: str, model_name: str) -> Any | None:
    """Return the named netbox-openbao model, or ``None`` when unavailable.

    An installed netbox-openbao may predate a model this module expects —
    ``ServiceEndpoint`` was added after some already-deployed baselines.
    ``apps.get_model()`` raises ``LookupError`` for a model the installed app
    doesn't define; that is "not available", not a bug to surface as a 500.
    """
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        return None


def resolve_node_ssh_from_device_openbao(
    node: Any,
    *,
    user: Any | None = None,
    port: int | None = None,
) -> dict | None:
    """Return SSH login material for ``node``'s linked device, or ``None``.

    ``None`` means "nothing to offer" and is safe for the caller to treat as
    a 404. A raised ``PermissionDenied`` means a match was found and refused
    — the caller must surface that as a failure, not keep looking.
    """
    device = getattr(node, "netbox_device", None)
    if device is None or not apps.is_installed("netbox_openbao"):
        return None
    if _node_ssh_access_disabled(node):
        raise PermissionDenied("SSH access is disabled for this node's endpoint.")

    endpoint = _match_openbao_endpoint(device, port=port)
    if endpoint is None:
        return None
    return _reveal_openbao_endpoint(node, endpoint, user=user)


def _node_ssh_access_disabled(node: Any) -> bool:
    """True when the node's owning Proxmox endpoint forbids SSH.

    Mirrors ``ssh_credentials._node_ssh_access_disabled`` for the local
    ``NodeSSHCredential`` path — disabled endpoints are a hard no-network
    gate for every SSH transport, including this fallback.
    """
    proxmox_endpoint = getattr(node, "endpoint", None)
    if proxmox_endpoint is None:
        return False
    return not proxmox_endpoint.ssh_access_enabled


def _match_openbao_endpoint(device: Any, *, port: int | None = None) -> Any | None:
    """Return the one credentialed SSH ``ServiceEndpoint`` for ``device``.

    Returns ``None`` when nothing matches, netbox-openbao doesn't define
    ``ServiceEndpoint`` yet, so the caller can report "no credential
    registered". Raises ``PermissionDenied`` when more than one candidate
    matches and ``port`` does not narrow it to exactly one.
    """
    service_endpoint_model = _get_openbao_model("netbox_openbao", "ServiceEndpoint")
    if service_endpoint_model is None:
        return None

    content_type = ContentType.objects.get_for_model(device)
    queryset = service_endpoint_model.objects.filter(
        assigned_object_type=content_type,
        assigned_object_id=device.pk,
        service_type=_SERVICE_TYPE_SSH,
        credential__isnull=False,
    )
    if port is not None:
        queryset = queryset.filter(port=port)

    candidates = list(queryset[:2])
    if not candidates:
        return None
    if len(candidates) > 1:
        logger.warning(
            "Refusing to resolve a device SSH credential for device %s: "
            "multiple credentialed SSH endpoints match. Narrow by port to "
            "disambiguate.",
            device.pk,
        )
        raise PermissionDenied(
            "Multiple credentialed SSH service endpoints match this device. "
            "Specify a port to disambiguate."
        )
    return candidates[0]


def _reveal_openbao_endpoint(
    node: Any, endpoint: Any, *, user: Any | None = None
) -> dict | None:
    """Reveal ``endpoint``'s credential material and shape the response payload.

    Verifies the credential's identity with an independent lookup keyed by
    ``endpoint.credential_id`` that also confirms the reverse relation back
    to this exact endpoint, rather than trusting a possibly stale cached
    ``endpoint.credential`` relation. The lookup is additionally restricted
    to the requesting user's own netbox-openbao ``reveal_credential`` object
    permission — the same authorization netbox-openbao's own reveal API
    applies (``Credential.objects.restrict(user, "reveal")``) — so a caller
    authorized only for the local ``NodeSSHCredential`` path cannot reveal an
    arbitrary device's OpenBao-stored material through this fallback.

    Returns ``None`` — "nothing to offer" — in the unlikely event
    netbox-openbao defines ``ServiceEndpoint`` but not ``Credential`` yet.
    """
    if not getattr(user, "is_authenticated", False):
        raise PermissionDenied(
            "An authenticated user is required to reveal OpenBao credential material."
        )
    credential_model = _get_openbao_model("netbox_openbao", "Credential")
    if credential_model is None:
        return None
    credential = (
        credential_model.objects.restrict(user, "reveal")
        .filter(pk=endpoint.credential_id, service_endpoints=endpoint.pk)
        .first()
    )
    if credential is None:
        raise PermissionDenied(
            "OpenBao service endpoint credential could not be verified, or "
            "the requesting user lacks reveal_credential permission on it."
        )
    if credential.credential_type not in _SSH_CREDENTIAL_TYPES:
        raise PermissionDenied(
            f"Credential {credential.pk} is not an SSH-shaped credential type."
        )

    is_keypair = credential.credential_type == _CREDENTIAL_TYPE_SSH_KEYPAIR
    material_field = "private_key" if is_keypair else "password"
    material = _reveal_material(credential, material_field, user=user)

    return {
        "node_id": node.pk,
        "username": credential.username,
        "port": endpoint.port or 22,
        "auth_method": "key" if is_keypair else "password",
        "known_host_fingerprint": "",
        "sudo_required": False,
        "has_password": not is_keypair,
        "has_private_key": is_keypair,
        "password": "" if is_keypair else material,
        "private_key": material if is_keypair else "",
    }


def _reveal_material(
    credential: Any, material_field: str, *, user: Any | None = None
) -> str:
    """Resolve one required OpenBao field without exposing provider errors.

    Mirrors ``integrations.openbao``'s "never expose provider errors or
    material" contract for this reveal path.
    """
    message = (
        f"OpenBao did not return {material_field} material for credential "
        f"{getattr(credential, 'pk', None)}."
    )
    from netbox_proxbox.integrations.openbao import reveal_credential_material

    try:
        payload = reveal_credential_material(credential, user=user)
    except Exception:  # noqa: BLE001 - never expose provider errors or material
        raise PermissionDenied(message) from None
    material = payload.get(material_field) if isinstance(payload, dict) else None
    if not isinstance(material, str) or not material:
        raise PermissionDenied(message)
    return material
