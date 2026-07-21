"""Tests for the per-VM "Sync now" view, including endpoint scoping."""

from __future__ import annotations

from types import SimpleNamespace

from tests.conftest import load_plugin_module


class _FakeQuerySet:
    """Minimal chainable queryset stub that yields a fixed list of ids."""

    def __init__(self, values: list[int], *, recorder: dict | None = None):
        self._values = values
        self._recorder = recorder

    def filter(self, **kwargs):
        if self._recorder is not None:
            self._recorder.setdefault("filters", []).append(kwargs)
        return self

    def exclude(self, **kwargs):
        return self

    def distinct(self):
        return self

    def values_list(self, *_fields, flat=False):
        return self

    def __iter__(self):
        return iter(self._values)


def _load(monkeypatch):
    return load_plugin_module(
        "netbox_proxbox.views.vm_sync_now",
        monkeypatch=monkeypatch,
    )


def _install_fake_enqueue(monkeypatch, module, captured):
    def fake_enqueue(cls, *args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(get_absolute_url=lambda: "/core/jobs/57/")

    monkeypatch.setattr(module.ProxboxSyncJob, "enqueue", classmethod(fake_enqueue))


def test_vm_sync_now_view_enqueues_targeted_vm_bundle(monkeypatch):
    vm_sync_now = _load(monkeypatch)
    captured: dict[str, object] = {}
    request = SimpleNamespace(user=SimpleNamespace(username="root"))
    vm = SimpleNamespace(
        pk=253,
        cluster_id=None,
        get_absolute_url=lambda: "/virtualization/virtual-machines/253/",
    )

    monkeypatch.setattr(vm_sync_now, "get_object_or_404", lambda *args, **kwargs: vm)
    monkeypatch.setattr(
        vm_sync_now.ProxmoxEndpoint, "objects", _FakeQuerySet([1, 2, 3]), raising=False
    )
    _install_fake_enqueue(monkeypatch, vm_sync_now, captured)

    response = vm_sync_now.VirtualMachineSyncNowView().post(request, pk=253)

    assert captured["instance"] is None
    assert captured["user"] is request.user
    assert captured["queue_name"] == vm_sync_now.PROXBOX_SYNC_QUEUE_NAME
    assert captured["name"] == "Proxbox Sync: Virtual machine 253"
    assert captured["sync_types"] == list(vm_sync_now._VM_SYNC_NOW_SYNC_TYPES)
    assert captured["netbox_vm_ids"] == ["253"]
    assert response.url == "/virtualization/virtual-machines/253/"


def test_targeted_sync_scopes_to_the_vms_own_endpoint(monkeypatch):
    """Regression: a single-VM sync must not fan out to every enabled endpoint.

    A reporter with 8 Proxmox endpoints saw cluster/node preflight run against
    all 8 while syncing one VM, because the view passed every enabled endpoint
    id straight through to the job.
    """
    vm_sync_now = _load(monkeypatch)
    captured: dict[str, object] = {}
    request = SimpleNamespace(user=SimpleNamespace(username="root"))
    vm = SimpleNamespace(
        pk=59,
        cluster_id=10,
        get_absolute_url=lambda: "/virtualization/virtual-machines/59/",
    )

    monkeypatch.setattr(vm_sync_now, "get_object_or_404", lambda *args, **kwargs: vm)
    recorder: dict = {}
    monkeypatch.setattr(
        vm_sync_now.ProxmoxCluster,
        "objects",
        _FakeQuerySet([4], recorder=recorder),
        raising=False,
    )
    monkeypatch.setattr(
        vm_sync_now.ProxmoxEndpoint,
        "objects",
        _FakeQuerySet([1, 2, 3, 4, 5, 6, 7, 8]),
        raising=False,
    )
    _install_fake_enqueue(monkeypatch, vm_sync_now, captured)

    vm_sync_now.VirtualMachineSyncNowView().post(request, pk=59)

    assert captured["proxmox_endpoint_ids"] == [4], (
        "targeted VM sync must pass only the endpoint that hosts the VM"
    )
    assert {"netbox_cluster_id": 10} in recorder["filters"]


def test_targeted_sync_falls_back_to_all_endpoints_when_unresolvable(monkeypatch):
    """A VM with no reflected Proxmox cluster must still be discoverable."""
    vm_sync_now = _load(monkeypatch)
    captured: dict[str, object] = {}
    request = SimpleNamespace(user=SimpleNamespace(username="root"))
    vm = SimpleNamespace(
        pk=77,
        cluster_id=10,
        get_absolute_url=lambda: "/virtualization/virtual-machines/77/",
    )

    monkeypatch.setattr(vm_sync_now, "get_object_or_404", lambda *args, **kwargs: vm)
    monkeypatch.setattr(
        vm_sync_now.ProxmoxCluster, "objects", _FakeQuerySet([]), raising=False
    )
    monkeypatch.setattr(
        vm_sync_now.ProxmoxEndpoint, "objects", _FakeQuerySet([1, 2]), raising=False
    )
    _install_fake_enqueue(monkeypatch, vm_sync_now, captured)

    vm_sync_now.VirtualMachineSyncNowView().post(request, pk=77)

    assert captured["proxmox_endpoint_ids"] == [1, 2]
