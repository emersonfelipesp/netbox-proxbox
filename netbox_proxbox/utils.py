"""Helpers for backend host resolution, URL construction, and auth headers."""

from __future__ import annotations

import os
import subprocess
from typing import Any

from netbox_proxbox.type_defs import FastAPIAuthSource, FastAPIUrlDict, FastAPIUrlSource


def get_ip_address_host(value: Any) -> str:
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


def get_fastapi_url(endpoint: FastAPIUrlSource) -> FastAPIUrlDict:
    """Compute HTTP/WebSocket URLs and TLS settings for a FastAPI endpoint model."""
    ip = get_ip_address_host(getattr(endpoint, "ip_address", None))
    domain = getattr(endpoint, "domain", None) or ip
    websocket_domain = getattr(endpoint, "websocket_domain", None) or ip
    verify_ssl = bool(getattr(endpoint, "verify_ssl", False))

    scheme = "https" if verify_ssl else "http"
    websocket_scheme = "wss" if verify_ssl else "ws"
    http_url = f"{scheme}://{domain}:{endpoint.port}"
    websocket_url = f"{websocket_scheme}://{websocket_domain}:{endpoint.websocket_port}/ws"
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
        "domain": getattr(endpoint, "domain", None),
        "ip_address": getattr(endpoint, "ip_address", None),
        "ip_address_url": ip_address_url,
        "http_url": http_url,
        "websocket_url": websocket_url,
        "verify_ssl": verify_ssl,
    }
