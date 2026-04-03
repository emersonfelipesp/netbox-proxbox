"""Helpers for backend host resolution, URL construction, and auth headers."""

from __future__ import annotations

import os
import subprocess

from netbox_proxbox.schemas.backend_proxy import FastAPIUrlDict
from netbox_proxbox.type_defs import FastAPIAuthSource, FastAPIUrlSource


def get_ip_address_host(value: object | None) -> str:
    """Return dotted host part from an IPAddress-like value or default loopback."""
    if value is None:
        return "127.0.0.1"
    return str(value).split("/")[0]


def get_backend_auth_headers(endpoint: FastAPIAuthSource | None) -> dict[str, str]:
    """Build Authorization header dict for ProxBox backend requests."""
    if endpoint is None:
        return {}
    token = (getattr(endpoint, "token", "") or "").strip()
    if not token:
        return {}

    if token.startswith("Bearer ") or token.startswith("Token "):
        return {"Authorization": token}

    return {"Authorization": f"Bearer {token}"}


def get_fastapi_context(endpoint: FastAPIUrlSource) -> dict | None:
    """Build auth headers and URLs for a FastAPI endpoint.

    Returns a dict with http_url, ip_address_url, verify_ssl, and headers.
    Returns None if endpoint is None or no FastAPI endpoint is configured.
    """
    if endpoint is None:
        return None

    url_dict = get_fastapi_url(endpoint)
    raw = url_dict.model_dump() if hasattr(url_dict, "model_dump") else dict(url_dict)

    return {
        "http_url": raw.get("http_url"),
        "ip_address_url": raw.get("ip_address_url"),
        "verify_ssl": bool(raw.get("verify_ssl", True)),
        "headers": get_backend_auth_headers(endpoint),
    }


def get_first_fastapi_context() -> dict | None:
    """Get context for the first configured FastAPI endpoint, if any."""
    from netbox_proxbox.models import FastAPIEndpoint

    fastapi_obj = FastAPIEndpoint.objects.first()
    if fastapi_obj is None:
        return None
    return get_fastapi_context(fastapi_obj)


def get_fastapi_url(endpoint: FastAPIUrlSource) -> dict:
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
        except Exception:
            pass

    return {
        "domain": getattr(endpoint, "domain", None) or None,
        "ip_address": ip,
        "ip_address_url": ip_address_url,
        "http_url": http_url,
        "websocket_url": websocket_url,
        "verify_ssl": verify_ssl,
    }
