from __future__ import annotations

from types import SimpleNamespace

from tests.conftest import ResponseStub, load_plugin_module


def _json_request(method: str = "POST"):
    return SimpleNamespace(
        method=method,
        headers={
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
    )


def _browser_request(method: str = "POST"):
    return SimpleNamespace(method=method, headers={"Accept": "text/html"})


def test_sync_resource_uses_primary_fastapi_url(monkeypatch, fastapi_endpoint):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    requested = []

    monkeypatch.setattr(
        module.requests,
        "get",
        lambda url, params=None, verify=True, timeout=None: requested.append((url, params, verify))
        or ResponseStub({"ok": True}),
    )

    response = module.sync_devices(_json_request())
    assert response.status_code == 202
    assert response.payload["queued"] is True
    assert requested == [
        ("https://proxbox.local:8800/dcim/devices/create", None, True)
    ]


def test_sync_resource_falls_back_to_ip_url(monkeypatch, fastapi_endpoint):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    requested = []

    def fake_get(url, params=None, verify=True, timeout=None):
        requested.append((url, params, verify))
        if "proxbox.local" in url:
            raise RuntimeError("primary failed")
        return ResponseStub({"ok": True})

    monkeypatch.setattr(module.requests, "get", fake_get)

    response = module.sync_vm_backups(_json_request())
    assert response.status_code == 202
    assert response.payload["queued"] is True
    assert requested == [
        (
            "https://proxbox.local:8800/virtualization/virtual-machines/backups/all/create",
            {"delete_nonexistent_backup": True},
            True,
        ),
        (
            "https://10.0.0.5:8800/virtualization/virtual-machines/backups/all/create",
            {"delete_nonexistent_backup": True},
            False,
        ),
    ]


def test_sync_resource_redirects_browser_requests_with_success_message(
    monkeypatch, fastapi_endpoint
):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )

    monkeypatch.setattr(module.requests, "get", lambda *args, **kwargs: ResponseStub({"ok": True}))

    response = module.sync_virtual_machines(_browser_request())

    assert response == {"redirect": "plugins:netbox_proxbox:home"}
    assert module._messages_stub.calls == [
        ("success", "Virtual machines sync queued successfully.")
    ]


def test_sync_resource_redirects_browser_requests_with_error_message(
    monkeypatch, fastapi_endpoint
):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )

    monkeypatch.setattr(module.requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    response = module.sync_full_update(_browser_request())

    assert response == {"redirect": "plugins:netbox_proxbox:home"}
    assert module._messages_stub.calls == [
        ("error", "Unable to reach the ProxBox backend.")
    ]
