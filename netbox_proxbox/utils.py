"""Helpers for backend host resolution, URL construction, and auth headers."""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from netbox_proxbox.type_defs import FastAPIAuthSource, FastAPIUrlSource

if TYPE_CHECKING:
    from django.http import HttpRequest
    from ipam.models import IPAddress


def resolve_ip_address_initial(value: object) -> "IPAddress | None":  # type: ignore[return-type]
    """Best-effort resolve a query-string IP address to an existing NetBox object."""
    from ipam.models import IPAddress

    if value is None:
        return None
    if isinstance(value, IPAddress):
        return value

    candidate = str(value).strip()
    if not candidate:
        return None

    if candidate.isdigit():
        ip_address = IPAddress.objects.filter(pk=candidate).first()
        if ip_address is not None:
            return ip_address
    return IPAddress.objects.filter(address=candidate).first()


def get_ip_address_host(value: object | None) -> str:
    """Return dotted host part from an IPAddress-like value or default loopback."""
    if value is None:
        return "127.0.0.1"
    return str(value).split("/")[0]


def get_backend_auth_headers(endpoint: FastAPIAuthSource | None) -> dict[str, str]:
    """Build auth header dict for ProxBox backend requests."""
    from netbox_proxbox.services.backend_key_adoption import (
        backend_key_runtime_is_trusted,
    )

    if endpoint is None or not backend_key_runtime_is_trusted(endpoint):
        return {}
    token = (getattr(endpoint, "token", "") or "").strip()
    if not token:
        return {}
    return {"X-Proxbox-API-Key": token}


def get_fastapi_context(endpoint: FastAPIUrlSource) -> dict[str, object] | None:
    """Build auth headers and URLs for a FastAPI endpoint.

    Returns a dict with http_url, ip_address_url, verify_ssl, and headers.
    Returns None if endpoint is None or no FastAPI endpoint is configured.
    """
    if endpoint is None:
        return None

    url_dict = get_fastapi_url(endpoint)

    return {
        "domain": url_dict.get("domain"),
        "http_url": url_dict.get("http_url"),
        "ip_address_url": url_dict.get("ip_address_url"),
        "websocket_url": url_dict.get("websocket_url"),
        "verify_ssl": bool(url_dict.get("verify_ssl", True)),
        "headers": get_backend_auth_headers(endpoint),
    }


def get_first_fastapi_context(
    endpoint_id: int | None = None,
) -> dict[str, object] | None:
    """Get context for the configured FastAPI endpoint.

    Args:
        endpoint_id: Optional specific endpoint ID. If not provided, selects by ID when multiple
            endpoints exist, or returns the only endpoint when only one exists.

    Returns:
        Context dict or None if no endpoints configured.
    """
    from netbox_proxbox.models import FastAPIEndpoint

    count = FastAPIEndpoint.objects.filter(enabled=True).count()
    if count == 0:
        return None

    if endpoint_id is not None:
        fastapi_obj = FastAPIEndpoint.objects.filter(
            pk=endpoint_id, enabled=True
        ).first()
        if fastapi_obj is None:
            return None
        return get_fastapi_context(fastapi_obj)

    if count == 1:
        fastapi_obj = FastAPIEndpoint.objects.filter(enabled=True).first()
        return get_fastapi_context(fastapi_obj) if fastapi_obj else None

    fastapi_obj = FastAPIEndpoint.objects.filter(enabled=True).order_by("pk").first()
    if fastapi_obj is None:
        return None
    return get_fastapi_context(fastapi_obj)


def get_fastapi_context_by_id(endpoint_id: int) -> dict[str, object] | None:
    """Get context for a specific FastAPI endpoint by ID.

    Args:
        endpoint_id: The primary key of the FastAPIEndpoint.

    Returns:
        Context dict or None if endpoint not found.
    """
    from netbox_proxbox.models import FastAPIEndpoint

    fastapi_obj = FastAPIEndpoint.objects.filter(pk=endpoint_id, enabled=True).first()
    if fastapi_obj is None:
        return None
    return get_fastapi_context(fastapi_obj)


def get_fastapi_context_for_request(request: HttpRequest) -> dict[str, object]:
    """Get FastAPI URL context for a request, respecting object-level permissions."""
    from netbox_proxbox.models import FastAPIEndpoint

    fastapi_endpoint = (
        FastAPIEndpoint.objects.restrict(request.user, "view")
        .filter(enabled=True)
        .first()
    )
    if fastapi_endpoint:
        return get_fastapi_url(fastapi_endpoint) or {}
    return {}


PROXBOX_TAG_SLUG = "proxbox"


def get_proxbox_tagged_object_ids(model_class: type) -> list[int]:
    """Return PKs of objects tagged 'proxbox' for a given model class.

    Centralises the repeated tag-lookup pattern used across resource list views
    so both UI and API layers can share the same query.
    """
    from django.contrib.contenttypes.models import ContentType
    from extras.models import Tag, TaggedItem

    proxbox_tag = Tag.objects.filter(slug=PROXBOX_TAG_SLUG).first()
    if not proxbox_tag:
        return []
    ct = ContentType.objects.get_for_model(model_class)
    qs = TaggedItem.objects.filter(tag=proxbox_tag, content_type=ct).values_list(
        "object_id", flat=True
    )
    return list(qs)


def resolve_vm_type(vm: object) -> str:
    """Return 'lxc' or 'qemu' for a VirtualMachine, preferring native VirtualMachineType."""
    vm_type_obj = getattr(vm, "virtual_machine_type", None)
    if vm_type_obj and hasattr(vm_type_obj, "slug"):
        slug = str(vm_type_obj.slug)
        if "lxc" in slug:
            return "lxc"
        if "qemu" in slug:
            return "qemu"
    cf = getattr(vm, "custom_field_data", None) or {}
    return str(cf.get("proxmox_vm_type") or cf.get("cf_proxmox_vm_type") or "qemu")


def has_virtual_machine_type_field(model_class: type[object]) -> bool:
    """Return True when the live NetBox VirtualMachine model has the 4.6 type FK."""
    meta = getattr(model_class, "_meta", None)
    if meta is None:
        return bool(getattr(model_class, "virtual_machine_type", None))
    try:
        meta.get_field("virtual_machine_type")
    except Exception:
        return False
    return True


def vm_type_select_related_fields(model_class: type[object]) -> tuple[str, ...]:
    """Return common VM select_related fields, adding VirtualMachineType only if present."""
    fields = ["site", "cluster", "role", "tenant", "platform"]
    if has_virtual_machine_type_field(model_class):
        fields.append("virtual_machine_type")
    return tuple(fields)


def filter_queryset_by_proxmox_vm_type(
    queryset: object,
    model_class: type[object],
    *,
    vm_type: str,
    vm_type_slug: str,
) -> object:
    """Filter a VirtualMachine queryset by Proxmox type across NetBox 4.5 and 4.6."""
    from django.db.models import Q

    legacy_filter = Q(custom_field_data__proxmox_vm_type=vm_type) | Q(
        custom_field_data__cf_proxmox_vm_type=vm_type
    )
    if has_virtual_machine_type_field(model_class):
        return queryset.filter(
            Q(virtual_machine_type__slug=vm_type_slug) | legacy_filter
        )
    return queryset.filter(legacy_filter)


def get_fastapi_url(endpoint: FastAPIUrlSource) -> dict[str, object]:
    """Compute HTTP/WebSocket URLs and TLS settings for a FastAPI endpoint model.

    The URL scheme (``http``/``https``, ``ws``/``wss``) is driven by the
    ``use_https`` flag on the endpoint. ``verify_ssl`` is reported alongside but
    governs only certificate verification on whatever connection the scheme
    selects — see issue #352 for the rationale.
    """
    from netbox_proxbox.services.backend_key_adoption import (
        BackendKeyAdoptionError,
        backend_key_runtime_is_trusted,
        backend_key_target,
        canonical_backend_authority,
    )

    if not backend_key_runtime_is_trusted(endpoint):
        return {}

    try:
        http_url, verify_ssl = backend_key_target(endpoint)
        parsed_http = urlsplit(http_url)
        use_https = parsed_http.scheme == "https"
        scheme = parsed_http.scheme
        websocket_scheme = "wss" if use_https else "ws"

        ip_resolver = getattr(endpoint, "backend_key_ip_address_for_trust", None)
        ip_source = (
            ip_resolver()
            if callable(ip_resolver)
            else getattr(endpoint, "ip_address", None)
        )
        ip_authority = canonical_backend_authority(ip_source)
        ip = ip_authority.strip("[]")
        ip_address_url = (
            f"{scheme}://{ip_authority}:{int(endpoint.port)}" if ip_authority else ""
        )

        use_websocket = bool(getattr(endpoint, "use_websocket", False))
        websocket_url = ""
        server_websocket_url = ""
        websocket_source = (
            getattr(endpoint, "websocket_domain", None)
            or ip_source
            or getattr(endpoint, "domain", None)
        )
        if websocket_source:
            websocket_domain = canonical_backend_authority(websocket_source)
            ws_port_value = getattr(endpoint, "websocket_port", None)
            ws_port = int(ws_port_value if ws_port_value is not None else endpoint.port)
            if not websocket_domain or not 1 <= ws_port <= 65535:
                raise BackendKeyAdoptionError(
                    "endpoint_websocket_invalid",
                    "Configure a valid WebSocket host and port.",
                )
            websocket_url = f"{websocket_scheme}://{websocket_domain}:{ws_port}/ws"
        elif use_websocket:
            raise BackendKeyAdoptionError(
                "endpoint_websocket_address_missing",
                "Configure a valid WebSocket host before connecting.",
            )
        if use_websocket and bool(getattr(endpoint, "server_side_websocket", False)):
            server_websocket_url = f"{websocket_scheme}://{parsed_http.netloc}/ws"
    except (BackendKeyAdoptionError, TypeError, ValueError):
        return {}

    if (
        use_https
        and verify_ssl
        and any(
            host in http_url
            for host in ("proxbox.backend.local", "localhost", "127.0.0.1")
        )
    ):
        try:
            ca_root_folder = subprocess.run(
                ["mkcert", "-CAROOT"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            os.environ["REQUESTS_CA_BUNDLE"] = f"/{ca_root_folder}/rootCA.pem"
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        except OSError as exc:
            import logging

            logging.getLogger(__name__).debug(
                "Unexpected error checking mkcert CA: %s", exc
            )

    return {
        "domain": getattr(endpoint, "domain", None) or None,
        "ip_address": ip,
        "ip_address_url": ip_address_url,
        "http_url": http_url,
        "websocket_url": websocket_url,
        "server_websocket_url": server_websocket_url,
        "use_https": use_https,
        "verify_ssl": verify_ssl,
    }
