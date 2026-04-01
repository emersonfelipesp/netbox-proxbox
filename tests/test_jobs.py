"""Tests for ProxboxSyncJob (imports and run path)."""

from __future__ import annotations

import importlib.util
import logging
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def proxbox_sync_job_module(monkeypatch):
    """Load jobs.py with stubs for netbox.jobs and netbox_proxbox.choices."""
    netbox_constants = types.ModuleType("netbox.constants")
    netbox_constants.RQ_QUEUE_DEFAULT = "default"
    monkeypatch.setitem(sys.modules, "netbox.constants", netbox_constants)

    netbox_jobs = types.ModuleType("netbox.jobs")

    class JobRunner:
        pass

    netbox_jobs.JobRunner = JobRunner
    monkeypatch.setitem(sys.modules, "netbox.jobs", netbox_jobs)

    choices_mod = types.ModuleType("netbox_proxbox.choices")
    choices_mod.SyncTypeChoices = SimpleNamespace(
        DEVICES="devices",
        STORAGE="storage",
        VIRTUAL_MACHINES="virtual-machines",
        VIRTUAL_MACHINES_BACKUPS="vm-backups",
        VIRTUAL_MACHINES_DISKS="vm-disks",
        VIRTUAL_MACHINES_SNAPSHOTS="vm-snapshots",
        NETWORK_INTERFACES="network-interfaces",
        IP_ADDRESSES="ip-addresses",
        ALL="all",
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.choices", choices_mod)

    root = Path(__file__).resolve().parents[1]
    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(root / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)
    models_mod = types.ModuleType("netbox_proxbox.models")

    class _ProxboxPluginSettings:
        @classmethod
        def get_solo(cls):
            return SimpleNamespace(
                use_guest_agent_interface_name=True,
                proxbox_fetch_max_concurrency=8,
            )

    models_mod.ProxboxPluginSettings = _ProxboxPluginSettings
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_mod)

    sys.modules.pop("netbox_proxbox.jobs", None)
    path = root / "netbox_proxbox" / "jobs.py"
    spec = importlib.util.spec_from_file_location("netbox_proxbox.jobs", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["netbox_proxbox.jobs"] = module
    spec.loader.exec_module(module)
    return module


def test_proxbox_sync_job_run_imports_from_services_not_views(
    monkeypatch, proxbox_sync_job_module
):
    """run() must call ``run_sync_stream`` with proxbox-api SSE paths."""
    captured: dict[str, object] = {}

    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        captured["called"] = "run_sync_stream"
        captured["path"] = path
        captured["query_params"] = query_params
        return ({"stream": True, "response": {"ok": True, "message": "ok"}}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    views_sync = types.ModuleType("netbox_proxbox.views.sync")
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views.sync", views_sync)

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices

    ProxboxSyncJob.run(
        job,
        sync_type=st.DEVICES,
        proxmox_endpoint_ids=None,
        netbox_endpoint_ids=None,
    )
    assert captured["called"] == "run_sync_stream"
    assert captured["path"] == "dcim/devices/create/stream"
    assert captured["query_params"]["use_guest_agent_interface_name"] == "true"
    assert job.job.save.call_count >= 1

    job.job.reset_mock()
    ProxboxSyncJob.run(job, sync_type=st.ALL)
    assert captured["called"] == "run_sync_stream"
    assert captured["path"] == (
        "virtualization/virtual-machines/interfaces/ip-address/create/stream"
    )

    job.job.reset_mock()
    ProxboxSyncJob.run(job, sync_type=st.VIRTUAL_MACHINES_DISKS)
    assert captured["path"] == (
        "virtualization/virtual-machines/virtual-disks/create/stream"
    )

    job.job.reset_mock()
    ProxboxSyncJob.run(job, sync_type=st.NETWORK_INTERFACES)
    assert captured["path"] == "dcim/devices/interfaces/create/stream"

    job.job.reset_mock()
    ProxboxSyncJob.run(job, sync_type=st.IP_ADDRESSES)
    assert captured["path"] == (
        "virtualization/virtual-machines/interfaces/ip-address/create/stream"
    )


def test_proxbox_sync_params_from_job_defaults(proxbox_sync_job_module):
    from types import SimpleNamespace

    fn = proxbox_sync_job_module.proxbox_sync_params_from_job
    st = proxbox_sync_job_module.SyncTypeChoices
    p = fn(SimpleNamespace(data=None))
    assert p["sync_types"] == [st.ALL]
    assert p["proxmox_endpoint_ids"] == []
    assert p["netbox_endpoint_ids"] == []
    assert p["netbox_vm_ids"] == []


def test_is_proxbox_sync_job_by_queue_and_legacy_name(proxbox_sync_job_module):
    from types import SimpleNamespace

    fn = proxbox_sync_job_module.is_proxbox_sync_job
    qn = proxbox_sync_job_module.PROXBOX_SYNC_QUEUE_NAME
    legacy = proxbox_sync_job_module.LEGACY_PROXBOX_RQ_QUEUE
    assert fn(
        SimpleNamespace(
            queue_name=qn, name="Nightly DC1", data={"proxbox_sync": {"params": {}}}
        )
    )
    assert not fn(SimpleNamespace(queue_name=qn, name="Nightly DC1", data={}))
    assert not fn(SimpleNamespace(queue_name="other", name="Proxbox Sync", data={}))
    assert fn(SimpleNamespace(queue_name=legacy, name="Other", data={}))
    assert fn(SimpleNamespace(queue_name="", name="Proxbox Sync", data={}))
    assert fn(SimpleNamespace(queue_name=None, name="Proxbox Sync", data={}))


def test_proxbox_sync_params_from_job_stored(proxbox_sync_job_module):
    from types import SimpleNamespace

    fn = proxbox_sync_job_module.proxbox_sync_params_from_job
    st = proxbox_sync_job_module.SyncTypeChoices
    job = SimpleNamespace(
        data={
            "proxbox_sync": {
                "params": {
                    "sync_type": st.DEVICES,
                    "proxmox_endpoint_ids": ["1"],
                    "netbox_endpoint_ids": ["2"],
                    "netbox_vm_ids": ["248"],
                }
            }
        }
    )
    p = fn(job)
    assert p["sync_types"] == [st.DEVICES]
    assert p["proxmox_endpoint_ids"] == ["1"]
    assert p["netbox_endpoint_ids"] == ["2"]
    assert p["netbox_vm_ids"] == ["248"]


def test_proxbox_sync_params_from_job_stored_sync_types(proxbox_sync_job_module):
    from types import SimpleNamespace

    fn = proxbox_sync_job_module.proxbox_sync_params_from_job
    st = proxbox_sync_job_module.SyncTypeChoices
    job = SimpleNamespace(
        data={
            "proxbox_sync": {
                "params": {
                    "sync_types": [st.VIRTUAL_MACHINES, st.DEVICES],
                    "proxmox_endpoint_ids": [],
                    "netbox_endpoint_ids": [],
                }
            }
        }
    )
    p = fn(job)
    assert p["sync_types"] == [st.DEVICES, st.VIRTUAL_MACHINES]


def test_normalize_sync_types_orders_and_dedupes(proxbox_sync_job_module):
    st = proxbox_sync_job_module.SyncTypeChoices
    norm = proxbox_sync_job_module.normalize_sync_types
    out = norm(
        [
            st.VIRTUAL_MACHINES_BACKUPS,
            st.DEVICES,
            st.VIRTUAL_MACHINES,
            st.DEVICES,
        ]
    )
    assert out == [
        st.DEVICES,
        st.VIRTUAL_MACHINES,
        st.VIRTUAL_MACHINES_BACKUPS,
    ]


def test_normalize_sync_types_all_collapses(proxbox_sync_job_module):
    st = proxbox_sync_job_module.SyncTypeChoices
    norm = proxbox_sync_job_module.normalize_sync_types
    assert norm([st.ALL]) == [st.ALL]
    assert norm([st.DEVICES, st.ALL]) == [st.ALL]


def test_proxbox_sync_job_enqueue_default_job_timeout(
    monkeypatch, proxbox_sync_job_module
):
    """enqueue() must pass a long RQ job_timeout so workers do not kill SSE reads at ~300s."""
    captured: dict[str, object] = {}

    @classmethod
    def fake_enqueue(cls, *args, **kwargs):
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(
        sys.modules["netbox.jobs"].JobRunner,
        "enqueue",
        fake_enqueue,
        raising=False,
    )
    proxbox_sync_job_module.ProxboxSyncJob.enqueue(name="t", user=None, sync_type="all")
    assert (
        captured.get("job_timeout") == proxbox_sync_job_module.PROXBOX_SYNC_JOB_TIMEOUT
    )
    assert captured.get("sync_types") == ["all"]


def test_proxbox_sync_job_enqueue_respects_explicit_job_timeout(
    monkeypatch, proxbox_sync_job_module
):
    captured: dict[str, object] = {}

    @classmethod
    def fake_enqueue(cls, *args, **kwargs):
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(
        sys.modules["netbox.jobs"].JobRunner,
        "enqueue",
        fake_enqueue,
        raising=False,
    )
    proxbox_sync_job_module.ProxboxSyncJob.enqueue(
        name="t", user=None, sync_type="all", job_timeout=99999
    )
    assert captured.get("job_timeout") == 99999
    assert captured.get("sync_types") == ["all"]


def test_proxbox_sync_job_enqueue_accepts_sync_types_kwarg(
    monkeypatch, proxbox_sync_job_module
):
    captured: dict[str, object] = {}

    @classmethod
    def fake_enqueue(cls, *args, **kwargs):
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(
        sys.modules["netbox.jobs"].JobRunner,
        "enqueue",
        fake_enqueue,
        raising=False,
    )
    st = proxbox_sync_job_module.SyncTypeChoices
    proxbox_sync_job_module.ProxboxSyncJob.enqueue(
        name="t",
        user=None,
        sync_types=[st.VIRTUAL_MACHINES_DISKS, st.DEVICES],
    )
    assert captured.get("sync_types") == [st.DEVICES, st.VIRTUAL_MACHINES_DISKS]


def test_proxbox_sync_job_run_raises_on_backend_error(
    monkeypatch, proxbox_sync_job_module
):
    services_mod = types.ModuleType("netbox_proxbox.services")
    services_mod.run_sync_stream = lambda *a, **k: ({"detail": "unavailable"}, 503)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job")
    job.job = MagicMock()

    st = proxbox_sync_job_module.SyncTypeChoices
    with pytest.raises(RuntimeError, match="unavailable"):
        ProxboxSyncJob.run(job, sync_type=st.DEVICES)


def test_proxbox_sync_job_run_multi_stage_in_dependency_order(
    monkeypatch, proxbox_sync_job_module
):
    """Subset stages run sequentially: devices before vm-disks even if passed reversed."""
    paths: list[str] = []

    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        paths.append(path)
        return ({"stream": True, "response": {"ok": True}}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    views_sync = types.ModuleType("netbox_proxbox.views.sync")
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views.sync", views_sync)

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(
        job,
        sync_types=[st.VIRTUAL_MACHINES_DISKS, st.DEVICES],
    )
    assert paths == [
        "dcim/devices/create/stream",
        "virtualization/virtual-machines/virtual-disks/create/stream",
    ]
    saved = job.job.data
    assert "stages" in saved["proxbox_sync"]["response"]
    assert len(saved["proxbox_sync"]["response"]["stages"]) == 2


def test_proxbox_sync_job_run_targets_single_vm_route_when_requested(
    monkeypatch, proxbox_sync_job_module
):
    paths: list[str] = []

    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        paths.append(path)
        return ({"stream": True, "response": {"ok": True}}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(
        job,
        sync_types=[st.VIRTUAL_MACHINES],
        netbox_vm_ids=["248"],
    )
    assert paths == ["virtualization/virtual-machines/248/create/stream"]


def test_proxbox_sync_job_run_targets_each_requested_vm_related_route(
    monkeypatch, proxbox_sync_job_module
):
    paths: list[str] = []

    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        paths.append(path)
        return ({"stream": True, "response": {"ok": True}}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(
        job,
        sync_types=[
            st.VIRTUAL_MACHINES_SNAPSHOTS,
            st.VIRTUAL_MACHINES_BACKUPS,
            st.VIRTUAL_MACHINES_DISKS,
            st.VIRTUAL_MACHINES,
        ],
        netbox_vm_ids=["248", "512"],
    )
    assert paths == [
        "virtualization/virtual-machines/248/create/stream",
        "virtualization/virtual-machines/512/create/stream",
        "virtualization/virtual-machines/248/virtual-disks/create/stream",
        "virtualization/virtual-machines/512/virtual-disks/create/stream",
        "virtualization/virtual-machines/248/backups/create/stream",
        "virtualization/virtual-machines/512/backups/create/stream",
        "virtualization/virtual-machines/248/snapshots/create/stream",
        "virtualization/virtual-machines/512/snapshots/create/stream",
    ]


def test_proxbox_sync_job_run_targets_each_requested_vm_route(
    monkeypatch, proxbox_sync_job_module
):
    paths: list[str] = []

    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        paths.append(path)
        return ({"stream": True, "response": {"ok": True}}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(
        job,
        sync_types=[st.VIRTUAL_MACHINES],
        netbox_vm_ids=["248", "512", "777"],
    )
    assert paths == [
        "virtualization/virtual-machines/248/create/stream",
        "virtualization/virtual-machines/512/create/stream",
        "virtualization/virtual-machines/777/create/stream",
    ]


def test_proxbox_sync_job_query_flag_tracks_plugin_setting(
    monkeypatch, proxbox_sync_job_module
):
    captured: dict[str, object] = {}
    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        captured["query_params"] = query_params
        return ({"stream": True, "response": {"ok": True}}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)
    monkeypatch.setattr(
        proxbox_sync_job_module,
        "_use_guest_agent_interface_name_setting",
        lambda: False,
    )

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(job, sync_type=st.DEVICES)
    assert captured["query_params"]["use_guest_agent_interface_name"] == "false"
    assert captured["query_params"]["fetch_max_concurrency"] == "8"
    assert captured["query_params"]["ignore_ipv6_link_local_addresses"] == "true"


def test_proxbox_sync_job_query_uses_fetch_concurrency_setting(
    monkeypatch, proxbox_sync_job_module
):
    captured: dict[str, object] = {}
    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        captured["query_params"] = query_params
        return ({"stream": True, "response": {"ok": True}}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)
    monkeypatch.setattr(
        proxbox_sync_job_module,
        "_proxbox_fetch_max_concurrency_setting",
        lambda: 17,
    )

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(job, sync_type=st.DEVICES)
    assert captured["query_params"]["fetch_max_concurrency"] == "17"
    assert captured["query_params"]["ignore_ipv6_link_local_addresses"] == "true"


def test_proxbox_sync_job_query_flag_ignore_ipv6_link_local_setting(
    monkeypatch, proxbox_sync_job_module
):
    captured: dict[str, object] = {}
    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        captured["query_params"] = query_params
        return ({"stream": True, "response": {"ok": True}}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)
    monkeypatch.setattr(
        proxbox_sync_job_module,
        "_ignore_ipv6_link_local_addresses_setting",
        lambda: False,
    )

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(job, sync_type=st.DEVICES)
    assert captured["query_params"]["ignore_ipv6_link_local_addresses"] == "false"


def test_proxbox_sync_job_run_all_invokes_each_stage_stream(
    monkeypatch, proxbox_sync_job_module
):
    calls = 0

    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        nonlocal calls
        calls += 1
        return ({"stage": calls, "ok": True}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    views_sync = types.ModuleType("netbox_proxbox.views.sync")
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views.sync", views_sync)

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(job, sync_types=[st.ALL])
    assert calls == 8
    stages = job.job.data["proxbox_sync"]["response"]["stages"]
    assert len(stages) == 8
    assert {s["sync_type"] for s in stages} == {
        st.DEVICES,
        st.STORAGE,
        st.VIRTUAL_MACHINES,
        st.VIRTUAL_MACHINES_DISKS,
        st.VIRTUAL_MACHINES_BACKUPS,
        st.VIRTUAL_MACHINES_SNAPSHOTS,
        st.NETWORK_INTERFACES,
        st.IP_ADDRESSES,
    }
