"""Behavior tests for ``netbox_ceph.jobs._normalize_resources``.

Full ``CephSyncJob.run`` requires NetBox/Django bootstrap (Job model,
RQ queue, plugin settings rows), so the runtime path is covered in
integration. This module pins the smallest pure-Python piece of the
job — resource validation — which protects v1 from drifting away from
the proxbox-api ``/ceph/sync/*`` surface.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
JOBS_PATH = REPO_ROOT / "netbox_ceph" / "netbox_ceph" / "jobs.py"


def _install_jobs_module(monkeypatch: pytest.MonkeyPatch):
    for name in (
        "netbox_ceph",
        "netbox_ceph.services",
        "netbox_ceph.services.branch_lifecycle",
        "netbox_ceph.services.http_client",
        "netbox",
        "netbox.constants",
        "netbox.jobs",
    ):
        pkg = types.ModuleType(name)
        pkg.__path__ = []  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, name, pkg)

    sys.modules["netbox.constants"].RQ_QUEUE_DEFAULT = "default"  # type: ignore[attr-defined]

    class _JobRunner:
        class Meta:
            name = "Base"

        @classmethod
        def enqueue(cls, *args, **kwargs):  # pragma: no cover - not exercised here
            raise NotImplementedError

    sys.modules["netbox.jobs"].JobRunner = _JobRunner  # type: ignore[attr-defined]
    sys.modules["netbox.jobs"].Job = object  # type: ignore[attr-defined]

    bl = sys.modules["netbox_ceph.services.branch_lifecycle"]

    def _stub(*_a, **_k):
        return None

    bl.branching_enabled_settings = _stub  # type: ignore[attr-defined]
    bl.create_and_provision_branch = _stub  # type: ignore[attr-defined]
    bl.merge_branch = _stub  # type: ignore[attr-defined]

    hc = sys.modules["netbox_ceph.services.http_client"]
    hc.CEPH_SYNC_RESOURCES = (
        "status",
        "daemons",
        "osds",
        "pools",
        "filesystems",
        "crush",
        "flags",
        "full",
    )

    class _CephBackendError(RuntimeError):
        pass

    hc.CephBackendError = _CephBackendError  # type: ignore[attr-defined]
    hc.fetch_ceph_sync = _stub  # type: ignore[attr-defined]

    sys.modules.pop("netbox_ceph.jobs", None)
    spec = importlib.util.spec_from_file_location("netbox_ceph.jobs", JOBS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["netbox_ceph.jobs"] = module
    spec.loader.exec_module(module)
    return module


def test_default_resource_is_full(monkeypatch):
    mod = _install_jobs_module(monkeypatch)
    assert mod.DEFAULT_SYNC_RESOURCES == ("full",)
    assert mod._normalize_resources(None) == ["full"]
    assert mod._normalize_resources([]) == ["full"]


def test_resources_are_deduped_and_lowercased(monkeypatch):
    mod = _install_jobs_module(monkeypatch)
    assert mod._normalize_resources(["OSDS", "osds", "Pools", " flags "]) == [
        "osds",
        "pools",
        "flags",
    ]


def test_invalid_resource_raises(monkeypatch):
    mod = _install_jobs_module(monkeypatch)
    with pytest.raises(ValueError, match="Unknown Ceph sync resource"):
        mod._normalize_resources(["bogus"])


def test_ceph_sync_job_metadata(monkeypatch):
    mod = _install_jobs_module(monkeypatch)
    assert mod.CephSyncJob.Meta.name == "Ceph Sync"
    assert mod.CEPH_SYNC_QUEUE_NAME == "default"
    assert mod.CEPH_SYNC_JOB_TIMEOUT >= 7200
