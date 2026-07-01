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
DETAIL_TEMPLATE_PATH = (
    REPO_ROOT
    / "netbox_proxbox"
    / "templates"
    / "netbox_proxbox"
    / "proxmoxendpoint.html"
)
SSH_SETTINGS_TEMPLATE_PATH = (
    REPO_ROOT
    / "netbox_proxbox"
    / "templates"
    / "netbox_proxbox"
    / "proxmoxendpoint_ssh_settings.html"
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
    REPO_ROOT / "netbox_proxbox" / "migrations" / "0042_proxmoxendpoint_ssh_terminal.py"
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
    assert 'SSH_TERMINAL_ACTION = "open_ssh_terminal"' in access_src
    assert (
        "get_permission_for_model(ProxmoxEndpoint, SSH_TERMINAL_ACTION)" in access_src
    )
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


def test_terminal_session_creation_restricts_by_terminal_object_permission() -> None:
    src = VIEW_PATH.read_text()
    assert 'restrict(request.user, "view")' in src
    assert 'request.user, "open_ssh_terminal"' in src


def test_terminal_template_uses_xterm_and_exposes_no_backend_api_key() -> None:
    src = TEMPLATE_PATH.read_text()
    assert "vendor/xterm/xterm.css" in src
    assert "vendor/xterm/xterm.js" in src
    assert "js/ssh_terminal.js" in src
    assert "proxmoxendpoint_ssh_terminal_session" in src
    assert "X-Proxbox-API-Key" not in src


def test_endpoint_templates_show_write_and_ssh_source_state() -> None:
    detail_src = DETAIL_TEMPLATE_PATH.read_text()
    settings_src = SSH_SETTINGS_TEMPLATE_PATH.read_text()

    for src in (detail_src, settings_src):
        assert "object.allow_writes" in src
        assert "get_ssh_credential_source_display" in src
        assert "effective_ssh_username" in src

    assert "form.ssh_credential_source" in settings_src


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


def test_terminal_view_exposes_per_node_ready_and_store_capability() -> None:
    src = VIEW_PATH.read_text()
    # get_extra_context surfaces per-node stored-credential readiness and the
    # store-capability flag consumed by the modal.
    assert '"ssh_ready": node.pk in cred_node_ids' in src
    assert "can_store_credentials" in src
    assert "add_nodesshcredential" in src
    assert "change_nodesshcredential" in src
    assert "NodeSSHCredential.objects.filter(node__endpoint=instance)" in src


def test_terminal_session_view_handles_store_and_one_shot() -> None:
    src = VIEW_PATH.read_text()
    # Credential modal payload + store flag are read from the request body.
    assert 'credential = body.get("credential")' in src
    assert 'store = bool(body.get("store"))' in src
    # One-shot forwards inline creds to proxbox-api; store persists first.
    assert '"one_shot_credential"' in src
    assert "_apply_node_credential" in src
    # Validation/one-shot helpers now live in the standalone, unit-tested module
    # ssh_terminal_credential.py (behaviorally covered by
    # tests/test_ssh_terminal_credential.py).
    assert "validate_terminal_credential" in src
    assert "one_shot_payload" in src
    assert "from netbox_proxbox.views.endpoints.ssh_terminal_credential import" in src
    # Store path persists an encrypted NodeSSHCredential via the plugin key.
    assert "ProxboxPluginSettings.get_solo().encryption_key" in src
    assert "cred.set_private_key(" in src
    assert "cred.set_password(" in src
    assert "cred.full_clean()" in src


def test_terminal_session_view_preserves_security_gates() -> None:
    src = VIEW_PATH.read_text()
    # One-shot bypasses the stored-credential access gate, so the view enforces
    # the endpoint SSH access method explicitly, and store requires write perms +
    # an encryption key (503 when missing).
    assert "endpoint.ssh_access_enabled" in src
    assert "status=403" in src
    assert "status=503" in src
    # A fingerprint is mandatory for both paths — enforced by the extracted,
    # unit-tested validator module.
    helper_src = (
        REPO_ROOT
        / "netbox_proxbox"
        / "views"
        / "endpoints"
        / "ssh_terminal_credential.py"
    ).read_text()
    assert "Host-key fingerprint is required" in helper_src


def test_terminal_template_has_credential_modal() -> None:
    src = TEMPLATE_PATH.read_text()
    assert 'id="proxbox-ssh-cred-modal"' in src
    assert 'id="proxbox-cred-username"' in src
    assert 'id="proxbox-cred-fingerprint"' in src
    assert 'id="proxbox-cred-scan"' in src
    assert "Fetch host key" in src
    assert "Use once" in src
    assert "Store for future sessions" in src
    assert "data-can-store" in src
    # Data-API open/close trigger so the modal works without window.bootstrap.
    assert 'id="proxbox-cred-open"' in src
    assert 'data-bs-toggle="modal"' in src
    assert 'id="proxbox-cred-close"' in src
    # Never render untrusted content via innerHTML in the template scripts.
    assert "innerHTML" not in src
    assert "dangerouslySetInnerHTML" not in src


def test_terminal_javascript_drives_credential_modal() -> None:
    src = JS_PATH.read_text()
    for token in (
        "proxbox-ssh-cred-modal",
        "openCredentialModal",
        "submitCredential",
        "scanHostKey",
        "showModal",
        "modalOpenTrigger",
        "payload.credential",  # sends credential + store; backend maps to one_shot_credential
        "payload.store",
        "pendingCredential",
        "pendingStore",
        "host-key-fingerprint",
        "No SSH credential registered",  # error-frame fallback trigger
    ):
        assert token in src, token
    # Modal writes to the terminal/DOM via textContent, never innerHTML.
    assert "innerHTML" not in src
    assert "dangerouslySetInnerHTML" not in src
