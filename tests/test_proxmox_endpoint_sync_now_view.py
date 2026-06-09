"""Tests for ProxmoxEndpoint detail-page Sync Now behavior."""

from __future__ import annotations

from types import SimpleNamespace

from tests.conftest import load_plugin_module


def _load_module(monkeypatch):
    return load_plugin_module(
        "netbox_proxbox.views.endpoints.proxmox_sync_now",
        monkeypatch=monkeypatch,
    )


def _endpoint(*, enabled: bool = True):
    return SimpleNamespace(
        pk=5,
        name="pve-lab",
        enabled=enabled,
        get_absolute_url=lambda: "/plugins/proxbox/endpoints/proxmox/5/",
    )


def test_proxmox_endpoint_sync_now_enqueues_endpoint_scoped_full_sync(monkeypatch):
    sync_now = _load_module(monkeypatch)
    endpoint = _endpoint(enabled=True)
    captured: dict[str, object] = {}
    request = SimpleNamespace(user=SimpleNamespace(username="root"))

    monkeypatch.setattr(sync_now, "get_object_or_404", lambda *args, **kwargs: endpoint)
    monkeypatch.setattr(
        sync_now,
        "build_job_name",
        lambda action_label: f"Proxbox Sync: {action_label}",
    )

    def fake_enqueue(cls, *args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(get_absolute_url=lambda: "/core/jobs/57/")

    monkeypatch.setattr(
        sync_now.ProxboxSyncJob,
        "enqueue",
        classmethod(fake_enqueue),
    )

    response = sync_now.ProxmoxEndpointSyncNowView().post(request, pk=endpoint.pk)

    assert captured["instance"] is None
    assert captured["user"] is request.user
    assert captured["queue_name"] == sync_now.PROXBOX_SYNC_QUEUE_NAME
    assert captured["name"] == "Proxbox Sync: Proxmox endpoint pve-lab"
    assert captured["sync_types"] == [sync_now.SyncTypeChoices.ALL]
    assert captured["proxmox_endpoint_ids"] == ["5"]
    assert response.url == endpoint.get_absolute_url()


def test_proxmox_endpoint_sync_now_does_not_enqueue_disabled_endpoint(monkeypatch):
    sync_now = _load_module(monkeypatch)
    endpoint = _endpoint(enabled=False)
    request = SimpleNamespace(user=SimpleNamespace(username="root"))

    monkeypatch.setattr(sync_now, "get_object_or_404", lambda *args, **kwargs: endpoint)

    def fail_enqueue(cls, *args, **kwargs):
        raise AssertionError("disabled endpoint must not enqueue a sync job")

    monkeypatch.setattr(
        sync_now.ProxboxSyncJob,
        "enqueue",
        classmethod(fail_enqueue),
    )

    response = sync_now.ProxmoxEndpointSyncNowView().post(request, pk=endpoint.pk)

    assert response.url == endpoint.get_absolute_url()
    assert sync_now._messages_stub.calls == [
        ("warning", "Disabled Proxmox endpoints cannot run sync jobs.")
    ]


def test_proxmox_endpoint_sync_now_reports_enqueue_failure(monkeypatch):
    sync_now = _load_module(monkeypatch)
    endpoint = _endpoint(enabled=True)
    request = SimpleNamespace(user=SimpleNamespace(username="root"))
    errors: list[str] = []

    monkeypatch.setattr(sync_now, "get_object_or_404", lambda *args, **kwargs: endpoint)
    monkeypatch.setattr(
        sync_now,
        "notify_sync_error",
        lambda request, exc: errors.append(str(exc)),
    )

    def fail_enqueue(cls, *args, **kwargs):
        raise RuntimeError("queue offline")

    monkeypatch.setattr(
        sync_now.ProxboxSyncJob,
        "enqueue",
        classmethod(fail_enqueue),
    )

    response = sync_now.ProxmoxEndpointSyncNowView().post(request, pk=endpoint.pk)

    assert response.url == endpoint.get_absolute_url()
    assert errors == ["queue offline"]
