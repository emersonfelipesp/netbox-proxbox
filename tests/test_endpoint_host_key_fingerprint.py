"""Source contracts for the endpoint host-key fingerprint fetch feature.

The plugin proxies a host-key scan to proxbox-api and the SSH-settings tab
exposes a "Fetch host key" button that auto-fills the pinned fingerprint. The
real handshake correctness is proven by a live round-trip (Fetch -> Save ->
open terminal); these contracts pin the wiring, permission gate, graceful
backend-too-old mapping, and the button/JS so they do not silently regress.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "netbox_proxbox"

SSH_CRED_PATH = PLUGIN_ROOT / "api" / "ssh_credentials.py"
API_URLS_PATH = PLUGIN_ROOT / "api" / "urls.py"
TEMPLATE_PATH = (
    PLUGIN_ROOT / "templates" / "netbox_proxbox" / "proxmoxendpoint_ssh_settings.html"
)


def _classes(path: Path) -> set[str]:
    return {
        node.name
        for node in ast.parse(path.read_text()).body
        if isinstance(node, ast.ClassDef)
    }


def test_view_and_permission_classes_exist() -> None:
    classes = _classes(SSH_CRED_PATH)
    assert "ProxmoxEndpointHostKeyFingerprintAPIView" in classes
    assert "_ProxmoxEndpointChangePermission" in classes


def test_view_is_session_gated_by_change_permission() -> None:
    src = SSH_CRED_PATH.read_text()
    view_src = src.split("class ProxmoxEndpointHostKeyFingerprintAPIView", 1)[1]
    assert "permission_classes = [_ProxmoxEndpointChangePermission]" in view_src
    # Browser-session gate mirrors the SSH-settings tab permission.
    perm_src = src.split("class _ProxmoxEndpointChangePermission", 1)[1].split(
        "class ProxmoxEndpointHostKeyFingerprintAPIView", 1
    )[0]
    assert "netbox_proxbox.change_proxmoxendpoint" in perm_src
    assert "LOGIN_REQUIRED" in perm_src


def test_view_proxies_to_backend_host_key_endpoint() -> None:
    src = SSH_CRED_PATH.read_text()
    assert "import requests" in src
    assert "from netbox_proxbox.services.backend_context import" in src
    view_src = src.split("class ProxmoxEndpointHostKeyFingerprintAPIView", 1)[1]
    # Resolves host/port server-side from the endpoint.
    assert "endpoint.ssh_host" in view_src
    assert "endpoint.ssh_port" in view_src
    # Proxies to the proxbox-api scan route.
    assert "/ssh/host-key-fingerprint" in view_src
    # Carries the backend api-key headers + verify flag from the context.
    assert "ctx.headers" in view_src and "ctx.verify_ssl" in view_src


def test_view_degrades_gracefully_on_old_backend_and_errors() -> None:
    view_src = SSH_CRED_PATH.read_text().split(
        "class ProxmoxEndpointHostKeyFingerprintAPIView", 1
    )[1]
    # 404 from the backend (route missing) -> 503 "upgrade proxbox-api".
    assert "status_code == 404" in view_src
    assert "HTTP_503_SERVICE_UNAVAILABLE" in view_src
    # Unreachable backend -> 502.
    assert "HTTP_502_BAD_GATEWAY" in view_src
    # No resolvable host -> 422.
    assert "HTTP_422_UNPROCESSABLE_ENTITY" in view_src
    # Returns the scanned fingerprint for the form to consume.
    assert '"fingerprint"' in view_src


def test_url_registers_host_key_route() -> None:
    src = API_URLS_PATH.read_text()
    assert "ProxmoxEndpointHostKeyFingerprintAPIView" in src
    assert "by-endpoint/<int:endpoint_id>/host-key-fingerprint/" in src
    assert "api-ssh-credential-endpoint-host-key" in src


def test_template_has_fetch_button_and_fill_script() -> None:
    src = TEMPLATE_PATH.read_text()
    assert 'id="proxbox-fetch-host-key"' in src
    assert "Fetch host key" in src
    # JS builds the plugin API URL and fills the fingerprint input for review.
    assert "/host-key-fingerprint/" in src
    assert "id_ssh_known_host_fingerprint" in src
    # Only shown for saved endpoints (the SSH tab is edit-only anyway).
    assert "{% if object.pk %}" in src
