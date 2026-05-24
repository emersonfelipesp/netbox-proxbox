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
  a NetBox API token with ``view_nodesshcredential`` permission and refuses
  non-HTTPS in non-DEBUG mode.

The encryption key is read from ``ProxboxPluginSettings.encryption_key``;
when missing the secrets endpoint returns ``503 Service Unavailable``
rather than silently dropping the credential.
"""

from __future__ import annotations

from django.conf import settings as django_settings
from django.shortcuts import get_object_or_404
from netbox.api.authentication import TokenAuthentication
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from netbox_proxbox.models import (
    NodeSSHCredential,
    ProxboxPluginSettings,
    ProxmoxEndpoint,
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


def _endpoint_metadata_payload(endpoint: ProxmoxEndpoint) -> dict:
    return {
        "endpoint_id": endpoint.pk,
        "host": endpoint.ssh_host,
        "username": endpoint.ssh_username,
        "port": endpoint.ssh_port,
        "auth_method": endpoint.ssh_auth_method,
        "known_host_fingerprint": endpoint.ssh_known_host_fingerprint,
        "has_password": bool(endpoint.ssh_password_enc),
        "has_private_key": bool(endpoint.ssh_private_key_enc),
    }


def _credential_for_node_identifier(node_id: int) -> NodeSSHCredential:
    """Resolve credentials by ProxmoxNode PK, with NetBox device PK fallback.

    ``proxbox-api`` initially passed the linked ``dcim.Device`` id when fetching
    credentials. The primary lookup stays the intended ``ProxmoxNode`` id, while
    the fallback keeps that backend build compatible.
    """
    queryset = NodeSSHCredential.objects.select_related("node", "node__netbox_device")
    try:
        return queryset.get(node_id=node_id)
    except NodeSSHCredential.DoesNotExist:
        return get_object_or_404(queryset, node__netbox_device_id=node_id)


class _NetBoxTokenPermission(BasePermission):
    """Allow only NetBox API tokens with all required permissions.

    Browser sessions are intentionally rejected: decrypted SSH secrets are only
    returned when the request carries a NetBox API token, which is the header
    shape sent by ``proxbox-api`` through ``netbox-sdk``.
    """

    required_permissions: tuple[str, ...] = ()

    def has_permission(self, request: Request, view: object) -> bool:  # type: ignore[override]
        auth = request.headers.get("Authorization", "")
        if not (auth.startswith("Token ") or auth.startswith("Bearer ")):
            return False
        try:
            auth_result = TokenAuthentication().authenticate(request)
        except Exception:
            return False
        if not auth_result:
            return False
        user, _token = auth_result
        if not getattr(user, "is_authenticated", False):
            return False
        has_perm = getattr(user, "has_perm", None)
        return bool(
            callable(has_perm)
            and all(has_perm(permission) for permission in self.required_permissions)
        )


class _NetBoxTokenCanViewNodeSSHCredential(_NetBoxTokenPermission):
    """Allow node credential secret reads for NetBox API-token callers."""

    required_permissions = ("netbox_proxbox.view_nodesshcredential",)


class _NetBoxTokenCanReadEndpointSSHCredential(_NetBoxTokenPermission):
    """Allow endpoint fallback secret reads for terminal-capable API-token callers."""

    required_permissions = (
        "netbox_proxbox.view_proxmoxendpoint",
        "netbox_proxbox.open_ssh_terminal",
    )


class NodeSSHCredentialByNodeAPIView(APIView):
    """Return metadata (no secrets) for the credential bound to ``node_id``."""

    @property
    def permission_classes(self) -> list:
        from netbox_proxbox.api.views import _ProxboxDashboardPermission

        return [_ProxboxDashboardPermission]

    def get(self, request: Request, node_id: int) -> Response:
        """Return metadata only; 404 if no row, never returns secrets."""
        cred = _credential_for_node_identifier(node_id)
        return Response(_metadata_payload(cred))


class NodeSSHCredentialSecretsAPIView(APIView):
    """Return the decrypted credential payload for proxbox-api.

    Requires a NetBox API token with ``view_nodesshcredential`` permission and
    refuses non-HTTPS in non-DEBUG mode. The response is intentionally minimal:
    just what ``proxmox_sdk.ssh.RemoteSSHClient`` needs.
    """

    permission_classes = [_NetBoxTokenCanViewNodeSSHCredential]

    def get(self, request: Request, node_id: int) -> Response:
        """Return decrypted secrets for proxbox-api API-token callers only."""
        if not django_settings.DEBUG and not request.is_secure():
            return Response(
                {"detail": "HTTPS required to retrieve SSH credentials."},
                status=status.HTTP_403_FORBIDDEN,
            )

        cred = _credential_for_node_identifier(node_id)
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


class ProxmoxEndpointSSHCredentialSecretsAPIView(APIView):
    """Return decrypted endpoint fallback SSH credentials for proxbox-api."""

    permission_classes = [_NetBoxTokenCanReadEndpointSSHCredential]

    def get(self, request: Request, endpoint_id: int) -> Response:
        """Return endpoint fallback SSH secrets for API-token callers only."""
        if not django_settings.DEBUG and not request.is_secure():
            return Response(
                {"detail": "HTTPS required to retrieve SSH credentials."},
                status=status.HTTP_403_FORBIDDEN,
            )

        endpoint = get_object_or_404(ProxmoxEndpoint.objects.all(), pk=endpoint_id)
        if not endpoint.has_ssh_terminal_credentials:
            return Response(
                {"detail": "No endpoint SSH fallback credential configured."},
                status=status.HTTP_404_NOT_FOUND,
            )

        settings_obj = ProxboxPluginSettings.get_solo()
        key = settings_obj.encryption_key or ""
        if not key:
            return Response(
                {"detail": _ENCRYPTION_KEY_MISSING},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            password = (
                endpoint.get_ssh_password(key=key) if endpoint.ssh_password_enc else ""
            )
            private_key = (
                endpoint.get_ssh_private_key(key=key)
                if endpoint.ssh_private_key_enc
                else ""
            )
        except enc_helpers.EncryptionError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        payload = _endpoint_metadata_payload(endpoint)
        payload["password"] = password
        payload["private_key"] = private_key
        return Response(payload)
