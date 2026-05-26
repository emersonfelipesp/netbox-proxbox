"""Tests for ProxboxSyncJob (imports and run path)."""

from __future__ import annotations

import json
import importlib.util
import logging
import sys
import types
import uuid
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
        BACKUP_ROUTINES="backup-routines",
        REPLICATIONS="replications",
        TASK_HISTORY="task-history",
        DEVICES="devices",
        STORAGE="storage",
        VIRTUAL_MACHINES="virtual-machines",
        VIRTUAL_MACHINES_BACKUPS="vm-backups",
        VIRTUAL_MACHINES_DISKS="vm-disks",
        VIRTUAL_MACHINES_SNAPSHOTS="vm-snapshots",
        NETWORK_INTERFACES="network-interfaces",
        VM_INTERFACES="vm-interfaces",
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
                ignore_ipv6_link_local_addresses=True,
                primary_ip_preference="ipv4",
            )

    class _ProxmoxEndpoint:
        objects = SimpleNamespace(
            values_list=lambda *a, **kw: [],
            all=lambda: [],
            filter=lambda **kw: [],
        )

    class _NetBoxEndpoint:
        objects = SimpleNamespace(all=lambda: [])

    models_mod.ProxboxPluginSettings = _ProxboxPluginSettings
    models_mod.ProxmoxEndpoint = _ProxmoxEndpoint
    models_mod.NetBoxEndpoint = _NetBoxEndpoint
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_mod)

    # Stub backend_auth so key-registration calls are no-ops in tests.
    backend_auth_mod = types.ModuleType("netbox_proxbox.services.backend_auth")
    backend_auth_mod.ensure_backend_key_registered = lambda *a, **kw: (True, "stubbed")
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.backend_auth", backend_auth_mod
    )

    # Stub backend_context so _ensure_backend_endpoints returns early (no FastAPI URL).
    backend_context_mod = types.ModuleType("netbox_proxbox.services.backend_context")
    backend_context_mod.get_fastapi_request_context = lambda **kw: None
    backend_context_mod.get_fastapi_endpoint_with_token = lambda *a, **kw: (None, None)
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.backend_context", backend_context_mod
    )

    # Stub views.backend_sync with no-op sync helpers.
    views_backend_sync_mod = types.ModuleType("netbox_proxbox.views.backend_sync")
    views_backend_sync_mod.sync_netbox_endpoint_to_backend = lambda *a, **kw: (
        True,
        None,
        None,
    )
    views_backend_sync_mod.sync_proxmox_endpoint_to_backend = lambda *a, **kw: (
        True,
        None,
        None,
    )
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.views.backend_sync", views_backend_sync_mod
    )

    # Stub netbox_proxbox.services.sync_cluster so the top-level import in jobs.py resolves.
    sync_cluster_mod = types.ModuleType("netbox_proxbox.services.sync_cluster")
    sync_cluster_mod.sync_cluster_and_nodes = lambda endpoint_id=None: SimpleNamespace(
        success=True,
        clusters_created=0,
        clusters_updated=0,
        nodes_created=0,
        nodes_updated=0,
        error=None,
    )
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.sync_cluster", sync_cluster_mod
    )

    # Stub netbox_proxbox.services.sync_firewall so the deferred import in jobs.py resolves.
    sync_firewall_mod = types.ModuleType("netbox_proxbox.services.sync_firewall")
    sync_firewall_mod.sync_firewall = lambda *a, **kw: SimpleNamespace(
        success=True,
        error=None,
        endpoint_id=None,
        endpoint_name="",
        endpoints_processed=0,
        security_groups_created=0,
        security_groups_updated=0,
        security_groups_stale=0,
        rules_created=0,
        rules_updated=0,
        rules_stale=0,
        ipsets_created=0,
        ipsets_updated=0,
        ipsets_stale=0,
        ipset_entries_created=0,
        ipset_entries_updated=0,
        ipset_entries_stale=0,
        aliases_created=0,
        aliases_updated=0,
        aliases_stale=0,
        options_created=0,
        options_updated=0,
        options_stale=0,
        per_endpoint=[],
    )
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.sync_firewall", sync_firewall_mod
    )

    # Stub sync_sdn so the deferred import in jobs.py resolves.
    sync_sdn_mod = types.ModuleType("netbox_proxbox.services.sync_sdn")
    sync_sdn_mod.sync_sdn = lambda *a, **kw: SimpleNamespace(
        success=True,
        error=None,
        endpoints_processed=0,
        fabrics_created=0,
        fabrics_updated=0,
        fabrics_stale=0,
        route_maps_created=0,
        route_maps_updated=0,
        route_maps_stale=0,
        prefix_lists_created=0,
        prefix_lists_updated=0,
        prefix_lists_stale=0,
        per_endpoint=[],
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services.sync_sdn", sync_sdn_mod)

    # Stub sync_datacenter so the deferred import in jobs.py resolves.
    sync_datacenter_mod = types.ModuleType("netbox_proxbox.services.sync_datacenter")
    sync_datacenter_mod.sync_datacenter = lambda *a, **kw: SimpleNamespace(
        success=True,
        error=None,
        endpoints_processed=0,
        cpu_models_created=0,
        cpu_models_updated=0,
        cpu_models_stale=0,
        per_endpoint=[],
    )
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.sync_datacenter", sync_datacenter_mod
    )

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
    captured: dict[str, object] = {"paths": []}

    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        captured["called"] = "run_sync_stream"
        captured["path"] = path
        captured["paths"].append(path)
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
    assert captured["path"] == "proxmox/cluster/backup/stream"

    job.job.reset_mock()
    ProxboxSyncJob.run(job, sync_type=st.VIRTUAL_MACHINES_DISKS)
    assert captured["path"] == (
        "virtualization/virtual-machines/virtual-disks/create/stream"
    )

    job.job.reset_mock()
    ProxboxSyncJob.run(job, sync_type=st.NETWORK_INTERFACES)
    assert captured["paths"][-2:] == [
        "dcim/devices/interfaces/create/stream",
        "virtualization/virtual-machines/interfaces/create/stream",
    ]

    job.job.reset_mock()
    ProxboxSyncJob.run(job, sync_type=st.IP_ADDRESSES)
    assert captured["path"] == (
        "virtualization/virtual-machines/interfaces/ip-address/create/stream"
    )


def test_proxbox_sync_job_network_interfaces_includes_vm_interfaces_stage(
    monkeypatch, proxbox_sync_job_module
):
    """network-interfaces sync must include both node and VM interface stages."""
    paths: list[str] = []

    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        paths.append(path)
        return ({"stream": True, "response": {"ok": True}}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job_network_interfaces")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(job, sync_type=st.NETWORK_INTERFACES)

    assert paths == [
        "dcim/devices/interfaces/create/stream",
        "virtualization/virtual-machines/interfaces/create/stream",
    ]


def test_proxbox_sync_job_skips_invalid_proxmox_endpoint_ids(
    monkeypatch, proxbox_sync_job_module, caplog
):
    """Malformed endpoint ids should be logged and skipped, not crash the job."""
    paths: list[str] = []
    synced_endpoint_ids: list[int] = []

    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        paths.append(path)
        return ({"stream": True, "response": {"ok": True}}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    sync_cluster_mod = sys.modules["netbox_proxbox.services.sync_cluster"]

    def sync_cluster_and_nodes(endpoint_id=None):
        synced_endpoint_ids.append(endpoint_id)
        return SimpleNamespace(
            success=True,
            clusters_created=0,
            clusters_updated=0,
            nodes_created=0,
            nodes_updated=0,
            error=None,
        )

    sync_cluster_mod.sync_cluster_and_nodes = sync_cluster_and_nodes
    monkeypatch.setattr(
        proxbox_sync_job_module.sync_stages,
        "effective_overwrites_for_endpoint",
        lambda _endpoint_id: {},
    )

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job_invalid_endpoint_ids")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    with caplog.at_level(logging.WARNING):
        ProxboxSyncJob.run(job, sync_type=st.DEVICES, proxmox_endpoint_ids=["bad", "2"])

    assert synced_endpoint_ids == [2]
    assert paths == ["dcim/devices/create/stream"]
    assert "Skipping invalid Proxmox endpoint id 'bad'" in caplog.text


def test_proxbox_sync_job_logs_stage_lines_with_rendered_values(
    monkeypatch, proxbox_sync_job_module, caplog
):
    """Stage logs should include concrete values (not '%s' placeholders)."""
    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        on_frame = stream_kwargs.get("on_frame")
        if on_frame:
            on_frame("step", {"step": "storage", "status": "processing"})
        return ({"stream": True, "response": {"ok": True}}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job_logs")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices

    with caplog.at_level(logging.INFO):
        ProxboxSyncJob.run(job, sync_type=st.STORAGE)

    joined = "\n".join(record.message for record in caplog.records)
    assert (
        "Starting stage: storage (virtualization/virtual-machines/storage/create/stream)"
        in joined
    )
    assert (
        "Stage completed: storage (virtualization/virtual-machines/storage/create/stream) HTTP 200"
        in joined
    )
    assert "%s" not in joined


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


def test_proxbox_sync_params_from_job_stored_batch_fields(proxbox_sync_job_module):
    from types import SimpleNamespace

    fn = proxbox_sync_job_module.proxbox_sync_params_from_job
    job = SimpleNamespace(
        data={
            "proxbox_sync": {
                "params": {
                    "sync_types": ["devices"],
                    "batch_object_type": "virtual-machine",
                    "batch_object_ids": ["10", "11"],
                }
            }
        }
    )

    p = fn(job)
    assert p["batch_object_type"] == "virtual-machine"
    assert p["batch_object_ids"] == ["10", "11"]


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


def test_proxbox_sync_params_from_legacy_vm_job_name(proxbox_sync_job_module):
    from types import SimpleNamespace

    fn = proxbox_sync_job_module.proxbox_sync_params_from_job
    st = proxbox_sync_job_module.SyncTypeChoices
    job = SimpleNamespace(
        name="Proxbox Sync: Virtual machine 249",
        data={"proxbox_sync": {"params": {"sync_type": st.ALL}}},
    )
    p = fn(job)
    assert p["sync_types"] == [
        st.VIRTUAL_MACHINES,
        st.VIRTUAL_MACHINES_BACKUPS,
        st.VIRTUAL_MACHINES_SNAPSHOTS,
    ]
    assert p["netbox_vm_ids"] == ["249"]


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


def test_proxbox_sync_job_enqueue_persists_targeted_vm_params(
    monkeypatch, proxbox_sync_job_module
):
    saved_updates: list[list[str]] = []

    class FakeJob:
        data = None

        def save(self, update_fields=None):
            saved_updates.append(list(update_fields or []))

    @classmethod
    def fake_enqueue(cls, *args, **kwargs):
        return FakeJob()

    monkeypatch.setattr(
        sys.modules["netbox.jobs"].JobRunner,
        "enqueue",
        fake_enqueue,
        raising=False,
    )

    st = proxbox_sync_job_module.SyncTypeChoices
    job = proxbox_sync_job_module.ProxboxSyncJob.enqueue(
        name="Proxbox Sync: Virtual machine 249",
        user=None,
        sync_types=[
            st.VIRTUAL_MACHINES,
            st.VIRTUAL_MACHINES_BACKUPS,
            st.VIRTUAL_MACHINES_SNAPSHOTS,
        ],
        netbox_vm_ids=["249"],
    )

    assert saved_updates == [["data"]]
    assert job.data["proxbox_sync"]["params"]["sync_types"] == [
        st.VIRTUAL_MACHINES,
        st.VIRTUAL_MACHINES_BACKUPS,
        st.VIRTUAL_MACHINES_SNAPSHOTS,
    ]
    assert job.data["proxbox_sync"]["params"]["sync_type"] == st.VIRTUAL_MACHINES
    assert job.data["proxbox_sync"]["params"]["netbox_vm_ids"] == ["249"]


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


def test_proxbox_sync_job_run_rewrites_postgres_slot_exhaustion_error(
    monkeypatch, proxbox_sync_job_module
):
    services_mod = types.ModuleType("netbox_proxbox.services")
    services_mod.run_sync_stream = lambda *a, **k: (
        {
            "detail": json.dumps(
                {
                    "error": (
                        'connection failed: connection to server at "127.0.0.1", '
                        "port 5432 failed: FATAL: remaining connection slots are "
                        "reserved for roles with the SUPERUSER attribute"
                    ),
                    "exception": "OperationalError",
                    "netbox_version": "4.5.5",
                    "python_version": "3.13.3",
                }
            )
        },
        500,
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job")
    job.job = MagicMock()

    st = proxbox_sync_job_module.SyncTypeChoices
    with pytest.raises(RuntimeError) as exc_info:
        ProxboxSyncJob.run(job, sync_type=st.DEVICES)

    error_text = str(exc_info.value)
    assert "no free PostgreSQL connections" in error_text
    assert "Wait for running jobs to finish" in error_text
    assert "remaining connection slots are reserved" not in error_text
    assert '{"error"' not in error_text


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


def test_proxbox_sync_job_persists_endpoint_runtime_breakdown(
    monkeypatch, proxbox_sync_job_module
):
    """Endpoint-scoped runs persist cards with local phases and SSE stage timings."""
    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        return ({"stream": True, "response": {"ok": True}, "path": path}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    class _EndpointQuerySet(list):
        def first(self):
            return self[0] if self else None

    class _EndpointManager:
        def filter(self, **kwargs):
            endpoints = [
                SimpleNamespace(pk=1, name="pve-a", effective_overwrites=lambda: {}),
                SimpleNamespace(pk=2, name="pve-b", effective_overwrites=lambda: {}),
            ]
            if "pk__in" in kwargs:
                ids = {int(value) for value in kwargs.get("pk__in", [])}
                return _EndpointQuerySet(
                    [endpoint for endpoint in endpoints if endpoint.pk in ids]
                )
            if "pk" in kwargs:
                return _EndpointQuerySet(
                    [
                        endpoint
                        for endpoint in endpoints
                        if endpoint.pk == int(kwargs["pk"])
                    ]
                )
            return _EndpointQuerySet(endpoints)

        def values_list(self, *args, **kwargs):
            return [1, 2]

    proxbox_sync_job_module.ProxmoxEndpoint.objects = _EndpointManager()

    sync_cluster_mod = sys.modules["netbox_proxbox.services.sync_cluster"]
    sync_cluster_mod.sync_cluster_and_nodes = lambda endpoint_id=None: SimpleNamespace(
        success=True,
        endpoint_id=endpoint_id,
        endpoint_name=f"pve-{endpoint_id}",
        clusters_created=0,
        clusters_updated=1,
        nodes_created=0,
        nodes_updated=2,
        error=None,
    )

    sys.modules["netbox_proxbox.services.sync_firewall"].sync_firewall = (
        lambda *a, **kw: SimpleNamespace(
            success=True,
            error=None,
            endpoints_processed=2,
            security_groups_created=0,
            security_groups_updated=0,
            rules_created=0,
            ipsets_created=0,
            aliases_created=0,
            per_endpoint=[
                {
                    "endpoint_id": 1,
                    "endpoint_name": "pve-1",
                    "success": True,
                    "runtime_seconds": 1.25,
                },
                {
                    "endpoint_id": 2,
                    "endpoint_name": "pve-2",
                    "success": True,
                    "runtime_seconds": 1.5,
                },
            ],
        )
    )
    sys.modules["netbox_proxbox.services.sync_sdn"].sync_sdn = lambda *a, **kw: (
        SimpleNamespace(
            success=True,
            error=None,
            endpoints_processed=2,
            fabrics_created=0,
            fabrics_updated=0,
            route_maps_created=0,
            route_maps_updated=0,
            prefix_lists_created=0,
            prefix_lists_updated=0,
            per_endpoint=[
                {
                    "endpoint_id": 1,
                    "endpoint_name": "pve-1",
                    "success": True,
                    "runtime_seconds": 0.5,
                },
                {
                    "endpoint_id": 2,
                    "endpoint_name": "pve-2",
                    "success": True,
                    "runtime_seconds": 0.75,
                },
            ],
        )
    )
    sys.modules["netbox_proxbox.services.sync_datacenter"].sync_datacenter = (
        lambda *a, **kw: SimpleNamespace(
            success=True,
            error=None,
            endpoints_processed=2,
            cpu_models_created=0,
            cpu_models_updated=0,
            cpu_models_stale=0,
            per_endpoint=[
                {
                    "endpoint_id": 1,
                    "endpoint_name": "pve-1",
                    "success": True,
                    "runtime_seconds": 0.25,
                },
                {
                    "endpoint_id": 2,
                    "endpoint_name": "pve-2",
                    "success": True,
                    "runtime_seconds": 0.35,
                },
            ],
        )
    )

    ticks = {"value": 100.0}

    def monotonic():
        ticks["value"] += 1.0
        return ticks["value"]

    monkeypatch.setattr(proxbox_sync_job_module.time, "monotonic", monotonic)

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_endpoint_runtime")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(job, sync_types=[st.DEVICES], proxmox_endpoint_ids=["1", "2"])

    response = job.job.data["proxbox_sync"]["response"]
    assert len(response["stages"]) == 2
    assert [stage["endpoint_id"] for stage in response["stages"]] == ["1", "2"]
    assert {stage["sync_type"] for stage in response["stages"]} == {st.DEVICES}

    endpoint_runtimes = response["endpoint_runtimes"]
    assert len(endpoint_runtimes) == 2
    assert {entry["endpoint_id"] for entry in endpoint_runtimes} == {1, 2}
    assert response["runtime_summary"]["endpoint_count"] == 2

    for entry in endpoint_runtimes:
        labels = [phase["label"] for phase in entry["phases"]]
        assert labels[:4] == [
            "Cluster/node sync",
            "Firewall sync",
            "SDN sync",
            "Datacenter sync",
        ]
        assert st.DEVICES in labels
        assert entry["runtime_seconds"] > 0


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
    captured_query_params: list[dict[str, object]] = []

    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        paths.append(path)
        captured_query_params.append(dict(query_params or {}))
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
    run_ids = {str(qp["run_id"]) for qp in captured_query_params}
    assert len(run_ids) == 1
    assert str(uuid.UUID(next(iter(run_ids)))) == next(iter(run_ids))


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
    assert captured["query_params"]["primary_ip_preference"] == "ipv4"


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
    assert captured["query_params"]["primary_ip_preference"] == "ipv4"


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
    assert captured["query_params"]["primary_ip_preference"] == "ipv4"


def test_full_sync_disables_vm_network_inside_virtual_machines_stage(
    monkeypatch, proxbox_sync_job_module
):
    captured: list[tuple[str, dict[str, object] | None]] = []
    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        captured.append((path, dict(query_params or {})))
        return ({"stream": True, "response": {"ok": True}}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(job, sync_types=[st.ALL])

    vm_stage = next(
        qp
        for path, qp in captured
        if path == "virtualization/virtual-machines/create/stream"
    )
    assert vm_stage["sync_vm_network"] == "false"
    vm_run_id = str(vm_stage["run_id"])
    assert str(uuid.UUID(vm_run_id)) == vm_run_id
    assert job.job.data["proxbox_sync"]["params"]["run_id"] == vm_run_id
    assert all(
        "run_id" not in qp
        for path, qp in captured
        if path != "virtualization/virtual-machines/create/stream"
    )


def test_vm_only_stage_keeps_default_vm_network_behavior(
    monkeypatch, proxbox_sync_job_module
):
    captured: list[tuple[str, dict[str, object] | None]] = []
    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        captured.append((path, dict(query_params or {})))
        return ({"stream": True, "response": {"ok": True}}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(job, sync_types=[st.VIRTUAL_MACHINES])

    vm_stage = next(
        qp
        for path, qp in captured
        if path == "virtualization/virtual-machines/create/stream"
    )
    assert "sync_vm_network" not in vm_stage
    assert str(uuid.UUID(str(vm_stage["run_id"]))) == vm_stage["run_id"]


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
    assert calls == 12
    stages = job.job.data["proxbox_sync"]["response"]["stages"]
    assert len(stages) == 12
    assert {s["sync_type"] for s in stages} == {
        st.DEVICES,
        st.STORAGE,
        st.VIRTUAL_MACHINES,
        st.TASK_HISTORY,
        st.VIRTUAL_MACHINES_DISKS,
        st.VIRTUAL_MACHINES_BACKUPS,
        st.VIRTUAL_MACHINES_SNAPSHOTS,
        st.REPLICATIONS,
        st.NETWORK_INTERFACES,
        st.VM_INTERFACES,
        st.IP_ADDRESSES,
        st.BACKUP_ROUTINES,
    }


def test_proxbox_sync_job_run_batch_selected_virtual_machines(
    monkeypatch, proxbox_sync_job_module
):
    batch_calls: list[dict[str, object]] = []

    async def _fake_batch(*args, **kwargs):
        batch_calls.append(kwargs)
        return {
            "batch_object_type": kwargs["batch_object_type"],
            "batch_object_label": "Virtual Machine",
            "total": len(kwargs["batch_object_ids"]),
            "succeeded": len(kwargs["batch_object_ids"]),
            "failed": 0,
            "results": [],
        }

    monkeypatch.setattr(
        proxbox_sync_job_module,
        "_run_batch_selected_sync",
        _fake_batch,
    )

    services_mod = types.ModuleType("netbox_proxbox.services")
    services_mod.run_sync_stream = lambda *args, **kwargs: ({"ok": True}, 200)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(
        job,
        sync_types=[st.ALL],
        batch_object_type="virtual-machine",
        batch_object_ids=["1", "2"],
    )

    assert batch_calls == [
        {
            "batch_object_type": "virtual-machine",
            "batch_object_ids": ["1", "2"],
            "netbox_branch_schema_id": None,
        }
    ]
    assert job.job.data["proxbox_sync"]["response"]["batch"]["total"] == 2


def test_stage_retries_on_502_then_succeeds(monkeypatch, proxbox_sync_job_module):
    """A 502 stream error on first attempt should trigger a retry that succeeds."""
    call_count = 0
    sleep_calls: list[float] = []

    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (
                {
                    "stream": True,
                    "detail": "ProxBox backend stream ended without a complete event.",
                },
                502,
            )
        return ({"stream": True, "response": {"ok": True}}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    import netbox_proxbox.sync_stages as ss

    monkeypatch.setattr(ss.time, "sleep", lambda s: sleep_calls.append(s))

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_retry_succeeds")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(job, sync_type=st.DEVICES)

    assert call_count == 2, "Expected one retry after initial 502"
    assert len(sleep_calls) == 1, "Expected one sleep between retries"


def test_stage_exhausts_retries_and_raises(monkeypatch, proxbox_sync_job_module):
    """When all retry attempts return 502, RuntimeError should be raised."""
    call_count = 0

    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        nonlocal call_count
        call_count += 1
        return (
            {
                "stream": True,
                "detail": "ProxBox backend stream ended without a complete event.",
            },
            502,
        )

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    import netbox_proxbox.sync_stages as ss

    monkeypatch.setattr(ss.time, "sleep", lambda s: None)

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_retry_exhausted")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    with pytest.raises(RuntimeError, match="stream ended without a complete event"):
        ProxboxSyncJob.run(job, sync_type=st.DEVICES)

    assert call_count == 3, "Expected 3 total attempts (1 + 2 retries)"


def test_stage_does_not_retry_on_4xx(monkeypatch, proxbox_sync_job_module):
    """A 4xx client error should not trigger retries."""
    call_count = 0

    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        nonlocal call_count
        call_count += 1
        return ({"detail": "Not Found"}, 404)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    import netbox_proxbox.sync_stages as ss

    sleep_calls: list[float] = []
    monkeypatch.setattr(ss.time, "sleep", lambda s: sleep_calls.append(s))

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_no_retry_4xx")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    with pytest.raises(RuntimeError):
        ProxboxSyncJob.run(job, sync_type=st.DEVICES)

    assert call_count == 1, "4xx should not be retried"
    assert len(sleep_calls) == 0, "No sleep for 4xx errors"


def test_proxbox_sync_job_query_flag_primary_ip_preference_setting(
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
        "_primary_ip_preference_setting",
        lambda: "ipv6",
    )

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(job, sync_type=st.DEVICES)
    assert captured["query_params"]["primary_ip_preference"] == "ipv6"


def test_proxbox_sync_job_full_update_uses_single_endpoint_overrides(
    monkeypatch, proxbox_sync_job_module
):
    """A full-update scoped to one endpoint must send all of that endpoint's flags."""
    captured: list[dict[str, object]] = []
    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        captured.append(dict(query_params or {}))
        return ({"stream": True, "response": {"ok": True}}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    overwrite_fields = tuple(
        proxbox_sync_job_module.sync_stages.effective_overwrites_for_endpoint(None)
    )
    assert len(overwrite_fields) == 25
    disabled_fields = {
        "overwrite_device_role",
        "overwrite_device_type",
        "overwrite_device_tags",
    }

    def effective_overwrites_for_endpoint(endpoint_id):
        assert str(endpoint_id) == "1"
        return {name: name not in disabled_fields for name in overwrite_fields}

    monkeypatch.setattr(
        proxbox_sync_job_module.sync_stages,
        "effective_overwrites_for_endpoint",
        effective_overwrites_for_endpoint,
    )

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job_endpoint_overrides")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(job, sync_types=[st.ALL], proxmox_endpoint_ids=["1"])

    assert captured
    assert {query["proxmox_endpoint_ids"] for query in captured} == {"1"}
    for query in captured:
        overwrite_keys = [key for key in query if key.startswith("overwrite_")]
        assert len(overwrite_keys) == 25
        assert set(overwrite_fields).issubset(query)
        for name in disabled_fields:
            assert query[name] == "false"


def test_proxbox_sync_job_loops_multiple_endpoint_scopes_with_distinct_overrides(
    monkeypatch, proxbox_sync_job_module
):
    """Multiple endpoint syncs run one SSE request per endpoint with flat flags."""
    captured: list[dict[str, object]] = []
    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        captured.append(dict(query_params or {}))
        return ({"stream": True, "response": {"ok": True}}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    overwrite_fields = tuple(
        proxbox_sync_job_module.sync_stages.effective_overwrites_for_endpoint(None)
    )
    assert len(overwrite_fields) == 25

    def effective_overwrites_for_endpoint(endpoint_id):
        disabled_fields = (
            {"overwrite_device_role", "overwrite_device_type", "overwrite_device_tags"}
            if str(endpoint_id) == "2"
            else set()
        )
        return {name: name not in disabled_fields for name in overwrite_fields}

    monkeypatch.setattr(
        proxbox_sync_job_module.sync_stages,
        "effective_overwrites_for_endpoint",
        effective_overwrites_for_endpoint,
    )

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job_multi_endpoint_overrides")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(job, sync_types=[st.DEVICES], proxmox_endpoint_ids=["1", "2"])

    assert [query["proxmox_endpoint_ids"] for query in captured] == ["1", "2"]
    for query in captured:
        overwrite_keys = [key for key in query if key.startswith("overwrite_")]
        assert len(overwrite_keys) == 25
        assert set(overwrite_fields).issubset(query)
    device_identity_flags = (
        "overwrite_device_role",
        "overwrite_device_type",
        "overwrite_device_tags",
    )
    assert {name: captured[0][name] for name in device_identity_flags} == {
        "overwrite_device_role": "true",
        "overwrite_device_type": "true",
        "overwrite_device_tags": "true",
    }
    assert {name: captured[1][name] for name in device_identity_flags} == {
        "overwrite_device_role": "false",
        "overwrite_device_type": "false",
        "overwrite_device_tags": "false",
    }
