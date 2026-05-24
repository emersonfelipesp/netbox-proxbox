"""Source contracts for the ProxmoxEndpoint browser SSH terminal surface."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = REPO_ROOT / "netbox_proxbox" / "models" / "proxmox_endpoint.py"
VIEW_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "endpoints" / "proxmox.py"
ACCESS_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "proxbox_access.py"
TEMPLATE_PATH = (
    REPO_ROOT
    / "netbox_proxbox"
    / "templates"
    / "netbox_proxbox"
    / "proxmoxendpoint_ssh_terminal.html"
)
JS_PATH = (
    REPO_ROOT
    / "netbox_proxbox"
    / "static"
    / "netbox_proxbox"
    / "js"
    / "ssh_terminal.js"
)
MIGRATION_PATH = (
    REPO_ROOT / "netbox_proxbox" / "migrations" / "0041_proxmoxendpoint_ssh_terminal.py"
)


def test_proxmox_endpoint_has_encrypted_ssh_fallback_fields() -> None:
    src = MODEL_PATH.read_text()
    for field_name in (
        "ssh_username",
        "ssh_port",
        "ssh_auth_method",
        "ssh_known_host_fingerprint",
        "ssh_password_enc",
        "ssh_private_key_enc",
    ):
        assert field_name in src
    assert "set_ssh_password" in src
    assert "get_ssh_private_key" in src
    assert "has_ssh_terminal_credentials" in src


def test_open_ssh_terminal_permission_is_declared() -> None:
    assert "open_ssh_terminal" in MODEL_PATH.read_text()
    assert "open_ssh_terminal" in MIGRATION_PATH.read_text()
    access_src = ACCESS_PATH.read_text()
    assert 'SSH_TERMINAL_PERMISSION = "netbox_proxbox.open_ssh_terminal"' in access_src
    assert "def permission_open_ssh_terminal" in access_src


def test_terminal_views_are_registered_and_backend_ticketed() -> None:
    src = VIEW_PATH.read_text()
    assert (
        '@register_model_view(ProxmoxEndpoint, "ssh_terminal", path="ssh-terminal")'
        in src
    )
    assert '"ssh_terminal_session"' in src
    assert 'path="ssh-terminal/session"' in src
    assert "permission_open_ssh_terminal()" in src
    assert "requests.post" in src
    assert '"ssh/sessions"' in src
    assert '"X-Proxbox-Actor"' in src


def test_terminal_template_uses_xterm_and_exposes_no_backend_api_key() -> None:
    src = TEMPLATE_PATH.read_text()
    assert "vendor/xterm/xterm.css" in src
    assert "vendor/xterm/xterm.js" in src
    assert "js/ssh_terminal.js" in src
    assert "proxmoxendpoint_ssh_terminal_session" in src
    assert "X-Proxbox-API-Key" not in src


def test_terminal_javascript_uses_ticket_protocol_without_backend_api_key() -> None:
    src = JS_PATH.read_text()
    for token in (
        'type: "auth"',
        'type: "input"',
        'type: "resize"',
        'type: "close"',
        "new WebSocket",
    ):
        assert token in src
    assert "X-CSRFToken" in src
    assert "X-Proxbox-API-Key" not in src
