"""Tests for test_vm_sync_now_view."""

from __future__ import annotations

from types import SimpleNamespace

from tests.conftest import load_plugin_module


def test_vm_sync_now_view_enqueues_targeted_vm_bundle(monkeypatch):
    vm_sync_now = load_plugin_module(
        "netbox_proxbox.views.vm_sync_now",
        monkeypatch=monkeypatch,
    )
    captured: dict[str, object] = {}
    request = SimpleNamespace(user=SimpleNamespace(username="root"))
    vm = SimpleNamespace(
        pk=253,
        get_absolute_url=lambda: "/virtualization/virtual-machines/253/",
    )

    monkeypatch.setattr(vm_sync_now, "get_object_or_404", lambda *args, **kwargs: vm)

    def fake_enqueue(cls, *args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(get_absolute_url=lambda: "/core/jobs/57/")

    monkeypatch.setattr(
        vm_sync_now.ProxboxSyncJob,
        "enqueue",
        classmethod(fake_enqueue),
    )

    response = vm_sync_now.VirtualMachineSyncNowView().post(request, pk=253)

    assert captured["instance"] is None
    assert captured["user"] is request.user
    assert captured["queue_name"] == vm_sync_now.PROXBOX_SYNC_QUEUE_NAME
    assert captured["name"] == "Proxbox Sync: Virtual machine 253"
    assert captured["sync_types"] == list(vm_sync_now._VM_SYNC_NOW_SYNC_TYPES)
    assert captured["netbox_vm_ids"] == ["253"]
    assert response.url == "/virtualization/virtual-machines/253/"
