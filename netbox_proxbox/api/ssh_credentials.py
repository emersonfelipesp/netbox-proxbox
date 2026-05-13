"""REST endpoints for SSH credential discovery.

proxbox-api fetches a node's stored credential over HTTPS before opening an
SSH session for hardware-discovery. The endpoint is split into two actions
so the dashboard UI never sees plaintext secrets while proxbox-api still has
a way to retrieve them:

* ``GET /api/plugins/proxbox/ssh-credentials/by-node/<node_id>/`` — metadata
  only (username, port, auth method, fingerprint, sudo flag, booleans
  indicating whether a secret is stored). Gated by
  ``_ProxboxDashboardPermission``.
* ``GET /api/plugins/proxbox/ssh-credentials/by-node/<node_id>/credentials/``
  — full payload including the decrypted password / private key. Requires
  a Bearer header matching ``FastAPIEndpoint.token`` (the proxbox-api
  backend) and refuses non-HTTPS in non-DEBUG mode.

The encryption key is read from ``ProxboxPluginSettings.encryption_key``;
when missing the secrets endpoint returns ``503 Service Unavailable``
rather than silently dropping the credential.
"""

from __future__ import annotations

from django.conf import settings as django_settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from netbox_proxbox.models import (
    FastAPIEndpoint,
    NodeSSHCredential,
    ProxboxPluginSettings,
)
from netbox_proxbox.utils import encryption as enc_helpers


_ENCRYPTION_KEY_MISSING = (
    "ProxboxPluginSettings.encryption_key is empty — refusing to return SSH "
    "secrets. Configure the encryption key in plugin settings first."
)


def _metadata_payload(cred: NodeSSHCredential) -> dict:
    return {
        "id": cred.pk,
        "node_id": cred.node_id,
        "username": cred.username,
        "port": cred.port,
        "auth_method": cred.auth_method,
        "known_host_fingerprint": cred.known_host_fingerprint,
        "sudo_required": cred.sudo_required,
        "has_password": bool(cred.password_enc),
        "has_private_key": bool(cred.private_key_enc),
    }


class _ProxboxBackendBearer(BasePermission):
    """Allow only the configured proxbox-api backend token to retrieve secrets.

    The token is compared against ``FastAPIEndpoint.token`` (the same value
    proxbox-api already uses to authenticate to this plugin's WebSocket /
    SSE bridges). Authentication is intentionally separate from NetBox
    user permissions: secrets must never be reachable from a browser
    session even with full ``view`` permission.
    """

    def has_permission(self, request: Request, view: object) -> bool:  # type: ignore[override]
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return False
        offered = auth[7:].strip()
        if not offered:
            return False
        endpoint = FastAPIEndpoint.objects.first()
        if endpoint is None or not endpoint.token:
            return False
        return offered == endpoint.token


class NodeSSHCredentialByNodeAPIView(APIView):
    """Return metadata (no secrets) for the credential bound to ``node_id``."""

    @property
    def permission_classes(self) -> list:
        from netbox_proxbox.api.views import _ProxboxDashboardPermission

        return [_ProxboxDashboardPermission]

    def get(self, request: Request, node_id: int) -> Response:
        """Return metadata only; 404 if no row, never returns secrets."""
        cred = get_object_or_404(NodeSSHCredential, node_id=node_id)
        return Response(_metadata_payload(cred))


class NodeSSHCredentialSecretsAPIView(APIView):
    """Return the decrypted credential payload for proxbox-api.

    Requires the Bearer token matching ``FastAPIEndpoint.token`` and
    refuses non-HTTPS in non-DEBUG mode. The response is intentionally
    minimal: just what ``proxmox_sdk.ssh.RemoteSSHClient`` needs.
    """

    permission_classes = [_ProxboxBackendBearer]

    def get(self, request: Request, node_id: int) -> Response:
        """Return decrypted secrets for proxbox-api Bearer callers only."""
        if not django_settings.DEBUG and not request.is_secure():
            return Response(
                {"detail": "HTTPS required to retrieve SSH credentials."},
                status=status.HTTP_403_FORBIDDEN,
            )

        cred = get_object_or_404(NodeSSHCredential, node_id=node_id)
        settings_obj = ProxboxPluginSettings.get_solo()
        key = settings_obj.encryption_key or ""
        if not key:
            return Response(
                {"detail": _ENCRYPTION_KEY_MISSING},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            password = cred.get_password(key=key) if cred.password_enc else ""
            private_key = cred.get_private_key(key=key) if cred.private_key_enc else ""
        except enc_helpers.EncryptionError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        payload = _metadata_payload(cred)
        payload["password"] = password
        payload["private_key"] = private_key
        return Response(payload)
