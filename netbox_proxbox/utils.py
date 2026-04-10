"""Helpers for backend host resolution, URL construction, and auth headers."""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

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
    if endpoint is None:
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
        "http_url": url_dict.get("http_url"),
        "ip_address_url": url_dict.get("ip_address_url"),
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

    count = FastAPIEndpoint.objects.count()
    if count == 0:
        return None

    if endpoint_id is not None:
        fastapi_obj = FastAPIEndpoint.objects.filter(pk=endpoint_id).first()
        if fastapi_obj is None:
            return None
        return get_fastapi_context(fastapi_obj)

    if count == 1:
        fastapi_obj = FastAPIEndpoint.objects.first()
        return get_fastapi_context(fastapi_obj) if fastapi_obj else None

    fastapi_obj = FastAPIEndpoint.objects.order_by("pk").first()
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

    fastapi_obj = FastAPIEndpoint.objects.filter(pk=endpoint_id).first()
    if fastapi_obj is None:
        return None
    return get_fastapi_context(fastapi_obj)


def get_fastapi_context_for_request(request: HttpRequest) -> dict[str, object]:
    """Get FastAPI URL context for a request, respecting object-level permissions."""
    from netbox_proxbox.models import FastAPIEndpoint

    fastapi_endpoint = FastAPIEndpoint.objects.restrict(request.user, "view").first()
    if fastapi_endpoint:
        return get_fastapi_url(fastapi_endpoint) or {}
    return {}


PROXBOX_TAG_SLUG = "proxbox"


def get_proxbox_tagged_object_ids(
    model_class: type, limit: int | None = None
) -> list[int]:
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
    if limit is not None:
        qs = qs[:limit]
    return list(qs)


def get_fastapi_url(endpoint: FastAPIUrlSource) -> dict[str, object]:
    """Compute HTTP/WebSocket URLs and TLS settings for a FastAPI endpoint model."""
    ip = get_ip_address_host(getattr(endpoint, "ip_address", None))
    domain = getattr(endpoint, "domain", None) or ip
    websocket_domain = getattr(endpoint, "websocket_domain", None) or ip
    verify_ssl = bool(getattr(endpoint, "verify_ssl", False))

    scheme = "https" if verify_ssl else "http"
    websocket_scheme = "wss" if verify_ssl else "ws"
    http_url = f"{scheme}://{domain}:{endpoint.port}"
    websocket_url = (
        f"{websocket_scheme}://{websocket_domain}:{endpoint.websocket_port}/ws"
    )
    ip_address_url = f"{scheme}://{ip}:{endpoint.port}"

    if verify_ssl and any(
        host in http_url for host in ("proxbox.backend.local", "localhost", "127.0.0.1")
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
        "verify_ssl": verify_ssl,
    }
