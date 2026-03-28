from __future__ import annotations

from tests.conftest import ResponseStub, load_plugin_module


class ImmediateThread:
    def __init__(self, *, target):
        self.target = target

    def start(self):
        self.target()


def test_sync_resource_uses_primary_fastapi_url(monkeypatch, fastapi_endpoint):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    requested = []

    monkeypatch.setattr(module, "Thread", ImmediateThread)
    monkeypatch.setattr(
        module.requests,
        "get",
        lambda url, params=None, verify=True: requested.append((url, params, verify))
        or ResponseStub({"ok": True}),
    )

    rendered = module.sync_devices(None)
    assert rendered["template"] == "netbox_proxbox/sync_devices.html"
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

    def fake_get(url, params=None, verify=True):
        requested.append((url, params, verify))
        if "proxbox.local" in url:
            raise RuntimeError("primary failed")
        return ResponseStub({"ok": True})

    monkeypatch.setattr(module, "Thread", ImmediateThread)
    monkeypatch.setattr(module.requests, "get", fake_get)

    rendered = module.sync_vm_backups(None)
    assert rendered["template"] == "netbox_proxbox/sync_vm_backups.html"
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
