"""Tests for test_sync."""

from __future__ import annotations

from types import SimpleNamespace

from tests.conftest import load_plugin_module

# Match ``SyncTypeChoices`` values without importing the plugin package at collection time.
ST_DEVICES = "devices"
ST_STORAGE = "storage"
ST_VMS = "virtual-machines"
ST_BACKUPS = "vm-backups"
ST_DISKS = "vm-disks"
ST_SNAPSHOTS = "vm-snapshots"
ST_ALL = "all"


def _post_request():
    return SimpleNamespace(
        method="POST",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        user=SimpleNamespace(
            is_authenticated=True,
            has_perms=lambda *a, **k: True,
            has_perm=lambda *a, **k: True,
        ),
    )


def _enqueue_spy(monkeypatch, module):
    calls: list[dict] = []

    class _FakeJob:
        def get_absolute_url(self):
            return "/core/jobs/1/"

    class _FakeProxboxSyncJob:
        @classmethod
        def enqueue(cls, **kwargs):
            calls.append(kwargs)
            return _FakeJob()

    monkeypatch.setattr(module, "ProxboxSyncJob", _FakeProxboxSyncJob)
    return calls


def test_sync_devices_enqueues_job_with_device_stage(monkeypatch, fastapi_endpoint):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    calls = _enqueue_spy(monkeypatch, module)

    response = module.sync_devices(_post_request())

    assert response == {"redirect": "plugins:netbox_proxbox:home"}
    assert len(calls) == 1
    assert calls[0]["sync_types"] == [ST_DEVICES]


def test_sync_virtual_machines_enqueues_correct_types(monkeypatch, fastapi_endpoint):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    calls = _enqueue_spy(monkeypatch, module)

    module.sync_virtual_machines(_post_request())

    assert calls[0]["sync_types"] == [ST_VMS, ST_DISKS]


def test_sync_storage_enqueues_storage_stage(monkeypatch, fastapi_endpoint):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    calls = _enqueue_spy(monkeypatch, module)

    module.sync_storage(_post_request())

    assert calls[0]["sync_types"] == [ST_STORAGE]


def test_sync_vm_backups_enqueues_backup_stage(monkeypatch, fastapi_endpoint):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    calls = _enqueue_spy(monkeypatch, module)

    module.sync_vm_backups(_post_request())

    assert calls[0]["sync_types"] == [ST_BACKUPS]


def test_sync_virtual_disks_enqueues_disk_stage(monkeypatch, fastapi_endpoint):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    calls = _enqueue_spy(monkeypatch, module)

    module.sync_virtual_disks(_post_request())

    assert calls[0]["sync_types"] == [ST_DISKS]


def test_sync_vm_snapshots_enqueues_snapshot_stage(monkeypatch, fastapi_endpoint):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    calls = _enqueue_spy(monkeypatch, module)

    module.sync_vm_snapshots(_post_request())

    assert calls[0]["sync_types"] == [ST_SNAPSHOTS]


def test_sync_full_update_enqueues_all_stages(monkeypatch, fastapi_endpoint):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    calls = _enqueue_spy(monkeypatch, module)

    module.sync_full_update(_post_request())

    assert calls[0]["sync_types"] == [ST_ALL]


def test_sync_success_message_mentions_job_link(monkeypatch, fastapi_endpoint):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    _enqueue_spy(monkeypatch, module)

    module.sync_devices(_post_request())

    assert module._messages_stub.calls
    kind, message = module._messages_stub.calls[0]
    assert kind == "success"
    assert "/core/jobs/1/" in str(message)


def test_sync_selected_virtual_machines_enqueues_batch_job(
    monkeypatch, fastapi_endpoint
):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    calls = _enqueue_spy(monkeypatch, module)

    request = _post_request()
    request.POST = SimpleNamespace(
        getlist=lambda key: ["11", "22"] if key == "pk" else []
    )

    module.SyncSelectedVirtualMachinesView().post(request)

    assert len(calls) == 1
    assert calls[0]["batch_object_type"] == "virtual-machine"
    assert calls[0]["batch_object_ids"] == ["11", "22"]


def test_sync_full_update_forwards_explicit_proxmox_endpoint_ids(
    monkeypatch, fastapi_endpoint, proxmox_endpoint
):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    calls = _enqueue_spy(monkeypatch, module)

    module.sync_full_update(_post_request())

    assert calls[0]["sync_types"] == [ST_ALL]
    assert calls[0]["proxmox_endpoint_ids"] == [proxmox_endpoint.pk]
