from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text()


def test_runtime_code_no_longer_depends_on_django_htmx():
    runtime_files = [
        "netbox_proxbox/views/keepalive_status.py",
        "netbox_proxbox/views/cards.py",
        "netbox_proxbox/views/sync.py",
        "netbox_proxbox/websocket_client.py",
        "netbox_proxbox/templates/netbox_proxbox/home.html",
        "netbox_proxbox/templates/netbox_proxbox/home/proxmox_card.html",
        "netbox_proxbox/templates/netbox_proxbox/home/netbox_card.html",
        "netbox_proxbox/templates/netbox_proxbox/home/fastapi_card.html",
        "netbox_proxbox/templates/netbox_proxbox/table/devices.html",
        "netbox_proxbox/templates/netbox_proxbox/table/virtual_machines.html",
    ]

    for path in runtime_files:
        contents = _read(path)
        assert "django_htmx" not in contents
        assert "hx-" not in contents


def test_home_template_uses_plugin_vanilla_js_entrypoint():
    contents = _read("netbox_proxbox/templates/netbox_proxbox/home.html")
    assert "netbox_proxbox/js/home.js" in contents
    assert "htmx.org" not in contents
    assert 'id="sync-progress-container"' in contents
    assert 'id="sync-progress-label"' in contents
    assert 'id="sync-progress-state"' in contents
    assert "progress-bar progress-bar-striped progress-bar-animated" in contents
    assert 'method="post"' in contents
    assert "{% csrf_token %}" in contents
    assert 'type="submit"' in contents
    assert "data-sync-url" in contents
    assert "data-sync-kind" in contents
    assert "data-sync-stream-url" in contents


def test_netbox_endpoint_edit_template_supports_v1_and_v2_tokens():
    contents = _read("netbox_proxbox/templates/netbox_proxbox/netboxendpoint_edit.html")
    assert "id_token_version" in contents
    assert "id_token" in contents
    assert "netbox-v1-token-field" in contents
    assert "netbox-v2-token-fields" in contents
    assert 'tokenVersionField.value === "v2"' in contents
    assert 'tokenField.value !== ""' in contents


def test_netbox_endpoint_home_card_uses_configured_token_state():
    contents = _read("netbox_proxbox/templates/netbox_proxbox/home/netbox_card.html")
    assert "object.token_version_label" in contents
    assert "object.has_configured_token" in contents


def test_home_javascript_passes_error_detail_to_badge_state():
    contents = _read("netbox_proxbox/static/netbox_proxbox/js/home.js")
    assert "setBadgeState(element, payload.status, payload.detail" in contents
    assert 'setBadgeState(element, "error", error.message' in contents
    assert "proxmox-connection-error-" in contents
    assert "payload.detail && badge" in contents
    assert 'form.addEventListener("submit"' in contents
    assert "function startSyncProgress(syncKind)" in contents
    assert 'function stopSyncProgress(status = "idle", detail = "")' in contents
    assert "startSyncProgress(syncKind)" in contents
    assert 'stopSyncProgress("success"' in contents
    assert 'stopSyncProgress("error"' in contents
    assert 'method: "POST"' in contents
    assert '"X-CSRFToken": getCsrfToken()' in contents
    assert '"X-Requested-With": "XMLHttpRequest"' in contents
    assert "request completed" in contents
    assert "streamSyncEvents" in contents
    assert 'Accept: "text/event-stream"' in contents


def test_common_badge_state_supports_hover_tooltip_details():
    contents = _read("netbox_proxbox/static/netbox_proxbox/js/common.js")
    assert 'element.dataset.bsToggle = "tooltip"' in contents
    assert "element.dataset.bsTitle = tooltip" in contents
    assert "export function getCsrfToken()" in contents
    assert "querySelector(\"input[name='csrfmiddlewaretoken']\")" in contents


def test_websocket_and_polling_modules_expose_sync_completion_hooks():
    websocket_contents = _read("netbox_proxbox/static/netbox_proxbox/js/websocket.js")
    polling_contents = _read("netbox_proxbox/static/netbox_proxbox/js/polling.js")

    assert "onSyncEnd(listener)" in websocket_contents
    assert "notifySyncEnd(syncObject)" in websocket_contents
    assert 'this.send("Full Update Sync")' in websocket_contents
    assert "callbacks = {}" in polling_contents
    assert "onComplete" in polling_contents
    assert "onError" in polling_contents


def test_proxmox_list_template_exposes_import_export_controls_and_warning_modal():
    contents = _read(
        "netbox_proxbox/templates/netbox_proxbox/proxmoxendpoint_list.html"
    )
    assert "proxmoxendpoint_bulk_import" in contents
    assert "proxmoxendpoint_export" in contents
    assert "Export JSON" in contents
    assert "Export YAML" in contents
    assert "Export with secrets" in contents
    assert 'name="format"' in contents
    assert (
        "This export includes Proxmox passwords and token values in plain text"
        in contents
    )
    assert 'name="netbox_token"' in contents
