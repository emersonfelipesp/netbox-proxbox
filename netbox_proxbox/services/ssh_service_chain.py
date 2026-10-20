"""Resolution and creation helpers for endpoint-owned SSH services."""

from __future__ import annotations

from typing import Any

try:
    from django.core.exceptions import ValidationError
except (ImportError, ModuleNotFoundError):  # isolated no-Django unit harness

    class ValidationError(ValueError):
        """Fallback used only while the mocked suite has no Django package."""


SSH_SERVICE_NAME = "ssh"
SSH_SERVICE_DESCRIPTION = "SSH remote login. Credentials are tied to this service."


def automatic_ssh_service_name(endpoint: Any, port: int) -> str:
    """Return a deterministic unused name without exposing existing services."""
    from netbox_proxbox.models import ProxmoxEndpointService

    if getattr(endpoint, "pk", None) is None:
        return SSH_SERVICE_NAME
    names = set(
        ProxmoxEndpointService.objects.filter(endpoint=endpoint).values_list(
            "name", flat=True
        )
    )
    for candidate in (SSH_SERVICE_NAME, f"{SSH_SERVICE_NAME}-{int(port)}"):
        if candidate not in names:
            return candidate
    suffix = 2
    while f"{SSH_SERVICE_NAME}-{int(port)}-{suffix}" in names:
        suffix += 1
    return f"{SSH_SERVICE_NAME}-{int(port)}-{suffix}"


def service_exposes_tcp_port(service: Any, port: int) -> bool:
    """Return whether a plugin application service exposes one TCP port."""
    return str(getattr(service, "protocol", "")).lower() == "tcp" and int(port) in {
        int(value) for value in (getattr(service, "ports", ()) or ())
    }


def service_ssh_port(service: Any, preferred: int = 22) -> int:
    """Select the preferred service port, or its lowest configured port."""
    ports = sorted({int(value) for value in (getattr(service, "ports", ()) or ())})
    if not ports:
        raise ValidationError("The selected application service has no ports.")
    if int(preferred) in ports:
        return int(preferred)
    return ports[0]


def find_ssh_service(
    endpoint: Any,
    ip_address: Any,
    port: int,
    queryset: Any = None,
) -> Any | None:
    """Find one visible matching endpoint service and reject ambiguity."""
    if endpoint is None or ip_address is None or getattr(endpoint, "pk", None) is None:
        return None
    if queryset is None:
        from netbox_proxbox.models import ProxmoxEndpointService

        queryset = ProxmoxEndpointService.objects.all()
    candidates = list(
        queryset.filter(
            endpoint=endpoint,
            protocol="tcp",
            ports__contains=[int(port)],
            ipaddresses=ip_address,
        ).order_by("pk")[:2]
    )
    if len(candidates) > 1:
        raise ValidationError(
            "More than one SSH application service exposes this endpoint IP address and port. Select one explicitly."
        )
    return candidates[0] if candidates else None


def build_ssh_service(
    endpoint: Any,
    ip_address: Any,
    port: int,
    *,
    name: str | None = None,
) -> Any:
    """Create and bind the default endpoint-owned SSH service."""
    from netbox_proxbox.models import ProxmoxEndpointService

    service = ProxmoxEndpointService(
        endpoint=endpoint,
        name=name or automatic_ssh_service_name(endpoint, port),
        protocol="tcp",
        ports=[int(port)],
        description=SSH_SERVICE_DESCRIPTION,
    )
    service.full_clean()
    service.save()
    service.ipaddresses.add(ip_address)
    return service
