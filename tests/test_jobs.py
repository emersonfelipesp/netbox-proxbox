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
        VIRTUAL_MACHINES="virtual-machines",
        VIRTUAL_MACHINES_BACKUPS="vm-backups",
        VIRTUAL_MACHINES_DISKS="vm-disks",
        ALL="all",
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.choices", choices_mod)

    root = Path(__file__).resolve().parents[1]
    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(root / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)

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
    assert job.job.save.call_count >= 1

    job.job.reset_mock()
    ProxboxSyncJob.run(job, sync_type=st.ALL)
    assert captured["called"] == "run_sync_stream"
    assert captured["path"] == "full-update/stream"

    job.job.reset_mock()
    ProxboxSyncJob.run(job, sync_type=st.VIRTUAL_MACHINES_DISKS)
    assert captured["path"] == (
        "virtualization/virtual-machines/virtual-disks/create/stream"
    )


def test_proxbox_sync_params_from_job_defaults(proxbox_sync_job_module):
    from types import SimpleNamespace

    fn = proxbox_sync_job_module.proxbox_sync_params_from_job
    st = proxbox_sync_job_module.SyncTypeChoices
    p = fn(SimpleNamespace(data=None))
    assert p["sync_type"] == st.ALL
    assert p["proxmox_endpoint_ids"] == []
    assert p["netbox_endpoint_ids"] == []


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
                }
            }
        }
    )
    p = fn(job)
    assert p["sync_type"] == st.DEVICES
    assert p["proxmox_endpoint_ids"] == ["1"]
    assert p["netbox_endpoint_ids"] == ["2"]


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
    assert captured.get("job_timeout") == proxbox_sync_job_module.PROXBOX_SYNC_JOB_TIMEOUT


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


def test_proxbox_sync_job_run_raises_on_backend_error(monkeypatch, proxbox_sync_job_module):
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
