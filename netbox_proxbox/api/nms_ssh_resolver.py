"""Resolve node SSH credentials from netbox-nms DeviceService when present."""

from __future__ import annotations

from django.apps import apps
from django.contrib.contenttypes.models import ContentType


def resolve_node_ssh_from_nms(node, *, user=None, request=None):
    """Return SSH login material from the linked device's netbox-nms SSH service."""
    device = getattr(node, "netbox_device", None)
    if device is None or not apps.is_installed("netbox_network"):
        return None

    from netbox_network.models import DeviceService

    parent_type = ContentType.objects.get_for_model(device)
    service = (
        DeviceService.objects.filter(
            assigned_object_type=parent_type,
            assigned_object_id=device.pk,
            service_type=DeviceService.SERVICE_SSH,
            enabled=True,
        )
        .select_related("credential")
        .first()
    )
    if service is None:
        service = (
            DeviceService.objects.filter(
                device=device,
                service_type=DeviceService.SERVICE_SSH,
                enabled=True,
            )
            .select_related("credential")
            .first()
        )
    if service is None or service.credential_id is None:
        return None

    credential = service.credential
    auth_method = credential.auth_method
    payload = {
        "node_id": node.pk,
        "username": credential.username,
        "port": service.port or 22,
        "auth_method": auth_method,
        "known_host_fingerprint": "",
        "sudo_required": False,
        "has_password": auth_method == credential.AUTH_METHOD_PASSWORD,
        "has_private_key": auth_method
        in (credential.AUTH_METHOD_KEY, credential.AUTH_METHOD_KEY_PASSPHRASE),
        "password": "",
        "private_key": "",
    }
    if auth_method == credential.AUTH_METHOD_PASSWORD:
        payload["password"] = credential.get_password(user=user, request=request)
    else:
        payload["private_key"] = credential.get_private_key(user=user, request=request)
    return payload
