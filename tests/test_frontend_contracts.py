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
