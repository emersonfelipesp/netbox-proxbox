"""Tests for ProxboxSyncJob (imports and run path)."""

from __future__ import annotations

import asyncio
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

from tests.django_stubs import DatabaseError, django_stub_modules

REPO_ROOT = Path(__file__).resolve().parents[1]

_REAL_BACKEND_SYNC: types.ModuleType | None = None


def load_real_backend_sync() -> types.ModuleType:
    """Path-load the **real** ``views/backend_sync.py`` against throwaway stubs.

    The preflight tests must exercise the real endpoint-identity predicates, not
    a hand-written mirror of them. This is not a style preference: a mirror is
    exactly what hid a security defect here for six review rounds. The fixture
    used to re-implement ``backend_holds_netbox_endpoint()`` "faithfully", and
    when the real helper was found to match two different domain-only NetBox
    instances against each other via the synthetic ``127.0.0.1`` push fallback,
    every test still passed — because the tests were asserting against the copy.
    A predicate that decides whether a sync may proceed using credentials the
    backend already holds has to be tested as itself.

    Only the pure predicates are taken from the loaded module; everything that
    performs HTTP is stubbed separately on the fixture's fake module, so nothing
    here can reach the network. Loaded once and cached: the module is stateless
    and the stubs below are private to this call.
    """
    global _REAL_BACKEND_SYNC
    if _REAL_BACKEND_SYNC is not None:
        return _REAL_BACKEND_SYNC

    saved = {
        name: sys.modules.get(name)
        for name in (
            "django.db",
            "django.utils.crypto",
            "netbox_proxbox",
            "netbox_proxbox.models",
            "netbox_proxbox.utils",
            "netbox_proxbox.services",
            "netbox_proxbox.services.endpoint_enabled",
            "netbox_proxbox.views",
            "netbox_proxbox.views.error_utils",
            "netbox_proxbox.views.backend_sync",
        )
    }
    try:
        # `backend_sync.py` imports `DatabaseError` and `salted_hmac` at module
        # level; without these the path-load dies with `No module named
        # 'django'`.  Shared with the other five loaders so the `salted_hmac`
        # implementation cannot drift — see `tests/django_stubs.py`.
        sys.modules.update(django_stub_modules())

        pkg = types.ModuleType("netbox_proxbox")
        pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
        sys.modules["netbox_proxbox"] = pkg

        views_pkg = types.ModuleType("netbox_proxbox.views")
        views_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "views")]
        sys.modules["netbox_proxbox.views"] = views_pkg

        models_mod = types.ModuleType("netbox_proxbox.models")
        models_mod.ProxmoxEndpoint = object
        sys.modules["netbox_proxbox.models"] = models_mod

        utils_mod = types.ModuleType("netbox_proxbox.utils")
        utils_mod.get_ip_address_host = lambda value: (
            str(value).split("/")[0] if value else "127.0.0.1"
        )
        sys.modules["netbox_proxbox.utils"] = utils_mod

        services_pkg = types.ModuleType("netbox_proxbox.services")
        services_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "services")]
        sys.modules["netbox_proxbox.services"] = services_pkg

        endpoint_enabled_mod = types.ModuleType(
            "netbox_proxbox.services.endpoint_enabled"
        )
        endpoint_enabled_mod.disabled_endpoint_detail = lambda *a, **kw: None
        sys.modules["netbox_proxbox.services.endpoint_enabled"] = endpoint_enabled_mod

        error_utils_mod = types.ModuleType("netbox_proxbox.views.error_utils")
        error_utils_mod.extract_backend_error_detail = lambda exc: (str(exc), None)
        error_utils_mod.parse_requests_response_json = lambda response, log_label=None: (
            response.json(),
            None,
        )
        sys.modules["netbox_proxbox.views.error_utils"] = error_utils_mod

        spec = importlib.util.spec_from_file_location(
            "netbox_proxbox.views.backend_sync",
            REPO_ROOT / "netbox_proxbox" / "views" / "backend_sync.py",
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["netbox_proxbox.views.backend_sync"] = module
        spec.loader.exec_module(module)
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

    _REAL_BACKEND_SYNC = module
    return module


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
    choices_mod.SyncModeChoices = SimpleNamespace(
        ALWAYS="always",
        BOOTSTRAP_ONLY="bootstrap_only",
        DISABLED="disabled",
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

    class _EndpointQuerySet(list):
        def first(self):
            return self[0] if self else None

        def values_list(self, field_name, flat=False):
            values = [getattr(item, field_name, item) for item in self]
            return values if flat else [(value,) for value in values]

    class _EndpointManager:
        rows: list = []

        @classmethod
        def all(cls):
            return _EndpointQuerySet(cls.rows)

        @classmethod
        def filter(cls, **kwargs):
            rows = list(cls.rows)
            if not rows and "pk__in" in kwargs:
                rows = [
                    SimpleNamespace(
                        pk=int(value),
                        enabled=True,
                        name=f"pve-{value}",
                        effective_overwrites=lambda: {},
                    )
                    for value in kwargs["pk__in"]
                ]
            if not rows and "pk" in kwargs:
                rows = [
                    SimpleNamespace(
                        pk=int(kwargs["pk"]),
                        enabled=True,
                        name=f"pve-{kwargs['pk']}",
                        effective_overwrites=lambda: {},
                    )
                ]
            if not rows and "pk__in" not in kwargs and "pk" not in kwargs:
                # An unfiltered lookup models a *normal* deployment: one enabled
                # Proxmox endpoint. Returning nothing here would put every run-level
                # test through the "no enabled Proxmox endpoint" fail-loud path in
                # sync_stages._run_all_stages_sync() — a state those tests never
                # meant to exercise. Tests that want the empty estate set
                # ``_EndpointManager.rows`` (or swap ProxmoxEndpoint) themselves.
                rows = [
                    SimpleNamespace(
                        pk=1,
                        enabled=True,
                        name="pve-1",
                        effective_overwrites=lambda: {},
                    )
                ]
            if "enabled" in kwargs:
                rows = [
                    row
                    for row in rows
                    if bool(getattr(row, "enabled", True)) is bool(kwargs["enabled"])
                ]
            if "pk__in" in kwargs:
                wanted = {int(value) for value in kwargs["pk__in"]}
                rows = [row for row in rows if int(getattr(row, "pk", row)) in wanted]
            if "pk" in kwargs:
                rows = [
                    row for row in rows if int(getattr(row, "pk", row)) == kwargs["pk"]
                ]
            return _EndpointQuerySet(rows)

        @classmethod
        def values_list(cls, field_name, flat=False):
            return cls.all().values_list(field_name, flat=flat)

    class _ProxmoxEndpoint:
        objects = _EndpointManager

    class _NetBoxEndpoint:
        # One enabled row, so the default preflight has something to push.
        objects = SimpleNamespace(
            all=lambda: [SimpleNamespace(pk=1, name="netbox-1")],
            filter=lambda **kwargs: [SimpleNamespace(pk=1, name="netbox-1")],
        )

    models_mod.ProxboxPluginSettings = _ProxboxPluginSettings
    models_mod.ProxmoxEndpoint = _ProxmoxEndpoint
    models_mod.NetBoxEndpoint = _NetBoxEndpoint
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_mod)

    # Stub backend_auth so key-registration calls are no-ops in tests.
    backend_auth_mod = types.ModuleType("netbox_proxbox.services.backend_auth")
    backend_auth_mod.ensure_backend_key_registered = lambda *a, **kw: (True, "stubbed")
    backend_auth_mod.wait_for_backend_ready = lambda *a, **kw: (True, "stubbed")
    backend_auth_mod.PREFLIGHT_READY_MAX_RETRIES = 5
    backend_auth_mod.PREFLIGHT_READY_INITIAL_DELAY = 1.0
    backend_auth_mod.PREFLIGHT_READY_MAX_DELAY = 8.0
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.backend_auth", backend_auth_mod
    )

    # Stub backend_context with a *usable* backend. A missing FastAPI endpoint is
    # a blocking preflight error now — every stage runs through that backend — so
    # the default fixture state has to be the healthy one. Preflight tests that
    # want the no-backend case override this per test.
    backend_context_mod = types.ModuleType("netbox_proxbox.services.backend_context")
    backend_context_mod.get_fastapi_request_context = lambda **kw: _preflight_context()
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
    views_backend_sync_mod.list_backend_netbox_endpoints = lambda *a, **kw: (
        [{"id": 1}],
        None,
    )
    views_backend_sync_mod.list_backend_proxmox_endpoints = lambda *a, **kw: (
        [],
        None,
    )
    views_backend_sync_mod.PREFLIGHT_ENDPOINT_PUSH_BUDGET = 600.0
    views_backend_sync_mod.PREFLIGHT_ENDPOINT_PUSH_HARD_CEILING = 1800.0

    # The three "may this run proceed on the credentials the backend holds?"
    # predicates are taken from the **real** module, never re-implemented here.
    # See `load_real_backend_sync()` for why: a hand-written mirror of
    # `backend_holds_netbox_endpoint()` is what let a security defect pass six
    # review rounds.
    _real_backend_sync = load_real_backend_sync()
    views_backend_sync_mod.backend_holds_proxmox_endpoint = (
        _real_backend_sync.backend_holds_proxmox_endpoint
    )
    views_backend_sync_mod.backend_holds_netbox_endpoint = (
        _real_backend_sync.backend_holds_netbox_endpoint
    )
    views_backend_sync_mod.netbox_push_credentials_unchanged = (
        _real_backend_sync.netbox_push_credentials_unchanged
    )
    views_backend_sync_mod.netbox_endpoint_credential_fingerprint = (
        _real_backend_sync.netbox_endpoint_credential_fingerprint
    )
    views_backend_sync_mod.proxmox_endpoint_credential_fingerprint = (
        _real_backend_sync.proxmox_endpoint_credential_fingerprint
    )
    views_backend_sync_mod.proxmox_push_credentials_unchanged = (
        _real_backend_sync.proxmox_push_credentials_unchanged
    )
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.views.backend_sync", views_backend_sync_mod
    )

    # Stub netbox_proxbox.services.sync_cluster so the top-level import in jobs.py resolves.
    sync_cluster_mod = types.ModuleType("netbox_proxbox.services.sync_cluster")
    sync_cluster_mod.sync_cluster_and_nodes = lambda endpoint_id=None, **kwargs: (
        SimpleNamespace(
            success=True,
            clusters_created=0,
            clusters_updated=0,
            nodes_created=0,
            nodes_updated=0,
            error=None,
        )
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

    # Stub sync_vm_template so the deferred import in jobs.py resolves.
    sync_vm_template_mod = types.ModuleType("netbox_proxbox.services.sync_vm_template")
    sync_vm_template_mod.sync_vm_templates = lambda endpoint_id=None, **kwargs: (
        SimpleNamespace(
            success=True,
            error=None,
            endpoint_id=endpoint_id,
            endpoint_name=f"pve-{endpoint_id}",
            endpoints_processed=1,
            templates_created=0,
            templates_updated=0,
            templates_skipped=0,
            templates_deleted=0,
            per_endpoint=[],
        )
    )
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.sync_vm_template", sync_vm_template_mod
    )

    sys.modules.pop("netbox_proxbox.jobs", None)
    path = root / "netbox_proxbox" / "jobs.py"
    spec = importlib.util.spec_from_file_location("netbox_proxbox.jobs", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["netbox_proxbox.jobs"] = module
    spec.loader.exec_module(module)

    # Resolve every scoped endpoint to a backend wire id of the same value. The real
    # helper queries proxbox-api, so without a default the enabled endpoint above
    # would land in the "never resolved to a backend id" fail-loud branch. Tests that
    # care about resolution failures monkeypatch this themselves and win, because
    # they run after the fixture.
    monkeypatch.setattr(
        module.sync_stages,
        "_resolve_wire_endpoint_ids",
        lambda scopes, **kwargs: (
            {scope[0]: scope[0] for scope in scopes if scope},
            None,
        ),
    )
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


def test_proxbox_sync_job_run_wires_vm_template_sync_per_endpoint(
    monkeypatch, proxbox_sync_job_module
):
    """The RQ sync job must call the dedicated VM-template service per endpoint."""
    paths: list[str] = []
    template_endpoint_ids: list[int] = []

    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        paths.append(path)
        return ({"stream": True, "response": {"ok": True}}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    def sync_vm_templates(endpoint_id=None, **kwargs):
        template_endpoint_ids.append(endpoint_id)
        return SimpleNamespace(
            success=True,
            error=None,
            endpoint_id=endpoint_id,
            endpoint_name=f"pve-{endpoint_id}",
            templates_created=1,
            templates_updated=2,
            templates_skipped=3,
            templates_deleted=4,
        )

    sys.modules[
        "netbox_proxbox.services.sync_vm_template"
    ].sync_vm_templates = sync_vm_templates
    monkeypatch.setattr(
        proxbox_sync_job_module.sync_stages,
        "_resolve_wire_endpoint_ids",
        lambda scopes, **kwargs: (
            {scope[0]: scope[0] + "00" for scope in scopes if scope},
            None,
        ),
    )

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job_vm_templates")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(job, sync_type=st.DEVICES, proxmox_endpoint_ids=["1", "2"])

    assert template_endpoint_ids == [1, 2]
    assert paths == ["dcim/devices/create/stream", "dcim/devices/create/stream"]
    endpoint_runtimes = job.job.data["proxbox_sync"]["response"]["endpoint_runtimes"]
    assert {
        phase["label"] for entry in endpoint_runtimes for phase in entry["phases"]
    } >= {"VM template sync"}


def test_proxbox_sync_job_skips_vm_template_sync_when_global_mode_disabled(
    monkeypatch, proxbox_sync_job_module
):
    """A globally disabled vm_template sync mode skips the job-level service call."""
    paths: list[str] = []
    template_endpoint_ids: list[int] = []

    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        paths.append(path)
        return ({"stream": True, "response": {"ok": True}}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)
    sys.modules["netbox_proxbox.services.sync_vm_template"].sync_vm_templates = (
        lambda endpoint_id=None, **kwargs: template_endpoint_ids.append(endpoint_id)
    )
    monkeypatch.setattr(
        proxbox_sync_job_module,
        "effective_sync_modes_for_endpoint",
        lambda _endpoint_id: {"sync_mode_vm_template": "disabled"},
    )
    monkeypatch.setattr(
        proxbox_sync_job_module.sync_stages,
        "_resolve_wire_endpoint_ids",
        lambda scopes, **kwargs: (
            {scope[0]: scope[0] + "00" for scope in scopes if scope},
            None,
        ),
    )

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job_vm_templates_disabled")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(job, sync_type=st.DEVICES, proxmox_endpoint_ids=["1"])

    assert template_endpoint_ids == []
    assert paths == ["dcim/devices/create/stream"]


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

    def sync_cluster_and_nodes(endpoint_id=None, **kwargs):
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
    # Plugin endpoint pks are translated to backend database ids before going on
    # the wire; stub that resolution (pk -> pk+"00") so no real backend is needed.
    monkeypatch.setattr(
        proxbox_sync_job_module.sync_stages,
        "_resolve_wire_endpoint_ids",
        lambda scopes, **kwargs: (
            {scope[0]: scope[0] + "00" for scope in scopes if scope},
            None,
        ),
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


def test_proxbox_sync_job_skips_disabled_explicit_proxmox_endpoint_ids(
    monkeypatch, proxbox_sync_job_module
):
    """Stale scheduled jobs must not sync disabled endpoint IDs."""
    streamed_queries: list[dict] = []
    synced_endpoint_ids: list[int] = []

    class _EndpointQuerySet(list):
        def first(self):
            return self[0] if self else None

        def values_list(self, field_name, flat=False):
            values = [getattr(item, field_name, item) for item in self]
            return values if flat else [(value,) for value in values]

    class _EndpointManager:
        rows = [
            SimpleNamespace(
                pk=1,
                enabled=False,
                name="disabled",
                effective_overwrites=lambda: {},
            ),
            SimpleNamespace(
                pk=2,
                enabled=True,
                name="enabled",
                effective_overwrites=lambda: {},
            ),
        ]

        @classmethod
        def filter(cls, **kwargs):
            rows = list(cls.rows)
            if "enabled" in kwargs:
                rows = [
                    row
                    for row in rows
                    if bool(getattr(row, "enabled", True)) is bool(kwargs["enabled"])
                ]
            if "pk__in" in kwargs:
                wanted = {int(value) for value in kwargs["pk__in"]}
                rows = [row for row in rows if int(row.pk) in wanted]
            return _EndpointQuerySet(rows)

        @classmethod
        def values_list(cls, field_name, flat=False):
            return _EndpointQuerySet(cls.rows).values_list(field_name, flat=flat)

    proxbox_sync_job_module.ProxmoxEndpoint.objects = _EndpointManager

    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        streamed_queries.append(dict(query_params or {}))
        return ({"stream": True, "response": {"ok": True}}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    sync_cluster_mod = sys.modules["netbox_proxbox.services.sync_cluster"]

    def sync_cluster_and_nodes(endpoint_id=None, **kwargs):
        synced_endpoint_ids.append(endpoint_id)
        return SimpleNamespace(
            success=True,
            endpoint_id=endpoint_id,
            endpoint_name=f"pve-{endpoint_id}",
            clusters_created=0,
            clusters_updated=0,
            nodes_created=0,
            nodes_updated=0,
            error=None,
        )

    sync_cluster_mod.sync_cluster_and_nodes = sync_cluster_and_nodes
    monkeypatch.setattr(
        proxbox_sync_job_module.sync_stages,
        "_resolve_wire_endpoint_ids",
        lambda scopes, **kwargs: (
            {scope[0]: scope[0] + "00" for scope in scopes if scope},
            None,
        ),
    )

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job_disabled_endpoint_ids")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(job, sync_type=st.DEVICES, proxmox_endpoint_ids=["1", "2"])

    assert synced_endpoint_ids == [2]
    assert [query["proxmox_endpoint_ids"] for query in streamed_queries] == ["200"]


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


def test_runtime_phase_status_requires_explicit_true(proxbox_sync_job_module):
    service_result = SimpleNamespace(
        per_endpoint=[
            {"endpoint_id": 1, "success": True},
            {"endpoint_id": 2, "success": False},
            {"endpoint_id": 3, "success": None},
            {"endpoint_id": 4},
        ]
    )

    service_phases = proxbox_sync_job_module._phases_from_service_result(
        service_result,
        kind="service",
        label="Service sync",
    )
    assert [phase["status"] for phase in service_phases] == [
        "success",
        "warning",
        "warning",
        "warning",
    ]

    stage_phases = proxbox_sync_job_module._phases_from_stage_results(
        [
            {"endpoint_id": 1, "result_summary": {"ok": True}},
            {"endpoint_id": 2, "result_summary": {"ok": False}},
            {"endpoint_id": 3, "result_summary": {"ok": None}},
            {"endpoint_id": 4, "result_summary": {}},
        ]
    )
    assert [phase["status"] for phase in stage_phases] == [
        "success",
        "warning",
        "warning",
        "warning",
    ]


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


# --------------------------------------------------------------------------- #
# ``fastapi_endpoint_id`` must survive a replay.
#
# ``job_run.py`` re-enqueues a finished job from
# ``proxbox_sync_params_from_job(job)``, and a recurring schedule re-enqueues
# itself the same way.  ``run()`` threads ``fastapi_endpoint_id`` through the
# preflight, key registration, wire-id resolution, and the four pre-SSE service
# passes -- so if the pin does not round-trip through ``job.data``, the replay
# silently re-elects "first enabled backend" and can certify one proxbox-api
# then sync against another.
# --------------------------------------------------------------------------- #


def _enqueue_capturing_job(monkeypatch, proxbox_sync_job_module, **kwargs):
    """Run ``ProxboxSyncJob.enqueue`` against a fake Job and return it."""

    class FakeJob:
        data = None
        name = kwargs.get("name", "t")

        def save(self, update_fields=None):
            pass

    @classmethod
    def fake_enqueue(cls, *args, **kw):
        return FakeJob()

    monkeypatch.setattr(
        sys.modules["netbox.jobs"].JobRunner,
        "enqueue",
        fake_enqueue,
        raising=False,
    )
    return proxbox_sync_job_module.ProxboxSyncJob.enqueue(user=None, **kwargs)


def test_enqueue_persists_fastapi_endpoint_id(monkeypatch, proxbox_sync_job_module):
    job = _enqueue_capturing_job(
        monkeypatch,
        proxbox_sync_job_module,
        name="t",
        sync_type="all",
        fastapi_endpoint_id=7,
    )
    assert job.data["proxbox_sync"]["params"]["fastapi_endpoint_id"] == 7


def test_enqueue_coerces_and_drops_unusable_fastapi_endpoint_id(
    monkeypatch, proxbox_sync_job_module
):
    """``job.data`` is a JSONField: store an int, or nothing at all."""
    job = _enqueue_capturing_job(
        monkeypatch,
        proxbox_sync_job_module,
        name="t",
        sync_type="all",
        fastapi_endpoint_id="7",
    )
    assert job.data["proxbox_sync"]["params"]["fastapi_endpoint_id"] == 7

    job = _enqueue_capturing_job(
        monkeypatch,
        proxbox_sync_job_module,
        name="t",
        sync_type="all",
        fastapi_endpoint_id="not-a-pk",
    )
    # A half-parsed pk would select a *different* backend than the caller meant,
    # which is worse than the documented "first enabled" fallback.
    assert "fastapi_endpoint_id" not in job.data["proxbox_sync"]["params"]


def test_enqueue_omits_fastapi_endpoint_id_when_unpinned(
    monkeypatch, proxbox_sync_job_module
):
    job = _enqueue_capturing_job(
        monkeypatch, proxbox_sync_job_module, name="t", sync_type="all"
    )
    assert "fastapi_endpoint_id" not in job.data["proxbox_sync"]["params"]


def test_enqueue_forwards_fastapi_endpoint_id_to_run(
    monkeypatch, proxbox_sync_job_module
):
    """The kwarg must also reach RQ, so the *original* run is pinned too."""
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
        name="t", user=None, sync_type="all", fastapi_endpoint_id=7
    )
    assert captured.get("fastapi_endpoint_id") == 7


@pytest.mark.parametrize("raw", [True, "not-a-pk", [], ""])
def test_enqueue_never_queues_a_pin_it_refused_to_store(
    monkeypatch, proxbox_sync_job_module, raw
):
    """The queued kwargs and ``job.data`` must not disagree about the pin.

    The kwarg handed to RQ is what reaches ``run()``; ``job.data`` is what a
    replay reads back. Coercing only on the way into ``job.data`` left an
    unusable value travelling to ``run()`` unchanged while the stored record
    said "unpinned" — so the first run and its replay could target different
    backends. ``True`` is the sharp one: a ``bool`` is an ``int`` in Python, so
    it survives every guard and Django resolves ``pk=True`` against primary key
    1, silently pinning whichever backend happens to be first.
    """
    captured: dict[str, object] = {}

    class FakeJob:
        data = None
        name = "t"

        def save(self, update_fields=None):
            pass

    @classmethod
    def fake_enqueue(cls, *args, **kwargs):
        captured.update(kwargs)
        return FakeJob()

    monkeypatch.setattr(
        sys.modules["netbox.jobs"].JobRunner,
        "enqueue",
        fake_enqueue,
        raising=False,
    )
    job = proxbox_sync_job_module.ProxboxSyncJob.enqueue(
        name="t", user=None, sync_type="all", fastapi_endpoint_id=raw
    )

    assert "fastapi_endpoint_id" not in captured
    assert "fastapi_endpoint_id" not in job.data["proxbox_sync"]["params"]


@pytest.mark.parametrize("raw", [True, "not-a-pk", []])
def test_run_recoerces_an_unusable_backend_pin_before_any_lookup(
    monkeypatch, proxbox_sync_job_module, raw
):
    """``run()`` cannot assume its caller normalised the pin.

    Direct callers, and RQ payloads queued by a release that predates the
    coercion in ``enqueue()``, still hand this a bool or an unparseable string.
    Every backend lookup downstream is a ``pk=`` filter, so the value has to be
    normalised at the entry point rather than trusted.
    """
    module = proxbox_sync_job_module
    seen: list[object] = []

    services_mod = types.ModuleType("netbox_proxbox.services")
    services_mod.run_sync_stream = lambda path, **kwargs: ({"response": {}}, 200)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    def _preflight(job, ids=None, fastapi_endpoint_id=None):
        seen.append(fastapi_endpoint_id)
        return module.PreflightResult(blocking_error="stop here")

    monkeypatch.setattr(module, "_ensure_backend_endpoints", _preflight)

    job = module.ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job_pin_recoercion")
    job.job = MagicMock()
    job.job.data = None

    with pytest.raises(module.ProxboxPreflightError):
        module.ProxboxSyncJob.run(
            job,
            sync_types=[module.SyncTypeChoices.DEVICES],
            proxmox_endpoint_ids=["1"],
            fastapi_endpoint_id=raw,
        )

    assert seen == [None], "an unusable pin must not reach a backend lookup"


def test_proxbox_sync_params_from_job_returns_fastapi_endpoint_id(
    proxbox_sync_job_module,
):
    from types import SimpleNamespace

    fn = proxbox_sync_job_module.proxbox_sync_params_from_job
    st = proxbox_sync_job_module.SyncTypeChoices
    job = SimpleNamespace(
        data={
            "proxbox_sync": {
                "params": {
                    "sync_types": [st.DEVICES],
                    "fastapi_endpoint_id": 7,
                }
            }
        }
    )
    assert fn(job)["fastapi_endpoint_id"] == 7


def test_proxbox_sync_params_from_job_omits_absent_fastapi_endpoint_id(
    proxbox_sync_job_module,
):
    from types import SimpleNamespace

    fn = proxbox_sync_job_module.proxbox_sync_params_from_job
    st = proxbox_sync_job_module.SyncTypeChoices
    job = SimpleNamespace(
        data={"proxbox_sync": {"params": {"sync_types": [st.DEVICES]}}}
    )
    # Absent, not ``None`` -- ``job_run.py`` splats this straight into
    # ``enqueue(**params)``, and an explicit ``None`` would still be "unpinned"
    # but adds a key nothing wrote.
    assert "fastapi_endpoint_id" not in fn(job)


def test_proxbox_sync_params_from_legacy_vm_job_name_keeps_fastapi_endpoint_id(
    proxbox_sync_job_module,
):
    """The legacy targeted-VM path rebuilds params from scratch -- it must not drop the pin."""
    from types import SimpleNamespace

    fn = proxbox_sync_job_module.proxbox_sync_params_from_job
    st = proxbox_sync_job_module.SyncTypeChoices
    job = SimpleNamespace(
        name="Proxbox Sync: Virtual machine 249",
        data={
            "proxbox_sync": {"params": {"sync_type": st.ALL, "fastapi_endpoint_id": 7}}
        },
    )
    params = fn(job)
    assert params["netbox_vm_ids"] == ["249"]
    assert params["fastapi_endpoint_id"] == 7


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (7, 7),
        ("7", 7),
        ("", None),
        ("abc", None),
        (True, None),
        (False, None),
        ([], None),
    ],
)
def test_coerce_fastapi_endpoint_id(proxbox_sync_job_module, value, expected):
    assert proxbox_sync_job_module._coerce_fastapi_endpoint_id(value) is expected


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

        def values_list(self, field_name, flat=False):
            values = [getattr(item, field_name, item) for item in self]
            return values if flat else [(value,) for value in values]

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

    # Plugin endpoint pks are translated to backend database ids before the wire
    # request; stub that resolution (pk -> pk+"00") so no real backend is needed.
    monkeypatch.setattr(
        proxbox_sync_job_module.sync_stages,
        "_resolve_wire_endpoint_ids",
        lambda scopes, **kwargs: (
            {scope[0]: scope[0] + "00" for scope in scopes if scope},
            None,
        ),
    )

    sync_cluster_mod = sys.modules["netbox_proxbox.services.sync_cluster"]
    sync_cluster_mod.sync_cluster_and_nodes = lambda endpoint_id=None, **kwargs: (
        SimpleNamespace(
            success=True,
            endpoint_id=endpoint_id,
            endpoint_name=f"pve-{endpoint_id}",
            clusters_created=0,
            clusters_updated=1,
            nodes_created=0,
            nodes_updated=2,
            error=None,
        )
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
        # The preflight push comes first — it is what gives the backend the
        # credentials the following phases rely on.
        assert labels[:4] == [
            "Backend endpoint push",
            "Cluster/node sync",
            "Firewall sync",
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
    assert len(stages) == 13
    assert any(
        stage["sync_type"] == "sdn" and stage["result_summary"].get("skipped") is True
        for stage in stages
    )
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
        "sdn",
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
            # The batch path must pin the same backend the preflight validated.
            "fastapi_endpoint_id": None,
            # …and the *Proxmox* side too. The fixture models one enabled
            # endpoint (pk 1) resolving to wire id "1", so the run must arrive
            # scoped to it. An unscoped batch is not a narrower request than a
            # scoped one — proxbox-api reads a missing filter as "sync every
            # endpoint I hold", including ones disabled in this NetBox.
            "proxmox_wire_endpoint_ids": "1",
            # The job-wide scope is the fallback; this map is what lets each
            # object be pinned to its *own* endpoint, because a cluster/node/
            # VMID is unique per endpoint and not across the estate.
            "proxmox_wire_endpoint_by_pk": {"1": "1"},
        }
    ]
    assert job.job.data["proxbox_sync"]["response"]["batch"]["total"] == 2
    # Same key and shape as the stage path, so the UI renders both identically.
    assert "endpoint_runtimes" in job.job.data["proxbox_sync"]["response"]


def test_batch_selected_sync_fails_the_job_when_selected_objects_failed(
    monkeypatch, proxbox_sync_job_module
):
    """A hand-picked run that did not sync everything is a failure, not a success.

    Every object in a selected-object run was named by an operator, so one that
    did not sync is a failed run — there is no "partial success" reading of a
    list somebody typed out. The batch path used to record the per-object
    failures in ``job.data`` and then return normally, leaving the job row
    **completed** and the errors visible only to someone who already suspected
    something was wrong.

    Two orderings are load-bearing and both are asserted here. ``job.data`` is
    persisted *before* the raise, so the failed row still carries the per-object
    detail an operator needs. And the raise happens *before* the branch merge,
    so a partial result is never promoted into main.
    """
    module = proxbox_sync_job_module
    merge_calls: list[dict[str, object]] = []

    async def _fake_batch(*args, **kwargs):
        return {
            "batch_object_type": kwargs["batch_object_type"],
            "batch_object_label": "Virtual Machine",
            "total": 2,
            "succeeded": 1,
            "failed": 1,
            "results": [
                {"object_id": "1", "status": 200},
                {
                    "object_id": "2",
                    "status": 424,
                    "error": "Proxmox endpoint 9 was skipped for this run",
                },
            ],
        }

    monkeypatch.setattr(module, "_run_batch_selected_sync", _fake_batch)

    services_mod = types.ModuleType("netbox_proxbox.services")
    services_mod.run_sync_stream = lambda *args, **kwargs: ({"ok": True}, 200)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    # Branching deliberately enabled: asserting the merge did not happen only
    # means something when it would otherwise have run. `run()` imports this
    # module lazily and guards only `ModuleNotFoundError`, so registering it in
    # `sys.modules` is what turns the merge on.
    branch_mod = types.ModuleType("netbox_proxbox.services.branch_lifecycle")
    branch_mod.branching_enabled_settings = lambda: {
        "prefix": "proxbox-sync",
        "on_conflict": "abort",
    }
    branch_mod.create_and_provision_branch = lambda **kwargs: SimpleNamespace(
        name=kwargs["name"], schema_id="branch-schema-1"
    )

    def _merge_branch(**kwargs):  # pragma: no cover - must not run
        merge_calls.append(kwargs)
        return True, "merged"

    branch_mod.merge_branch = _merge_branch
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.branch_lifecycle", branch_mod
    )

    job = module.ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job_batch_failure")
    job.job = MagicMock()
    job.job.data = None

    with pytest.raises(RuntimeError, match="Batch sync failed for") as excinfo:
        module.ProxboxSyncJob.run(
            job,
            sync_types=[module.SyncTypeChoices.ALL],
            batch_object_type="virtual-machine",
            batch_object_ids=["1", "2"],
        )

    message = str(excinfo.value)
    assert "Virtual Machine (2 total, 1 succeeded, 1 failed)" in message
    # The object that failed is named with its status and error, so the job-log
    # line alone says which record to look at.
    assert (
        "failed object(s): 2 (424: Proxmox endpoint 9 was skipped for this run)"
        in message
    )

    batch = job.job.data["proxbox_sync"]["response"]["batch"]
    assert batch["failed"] == 1
    assert [item["object_id"] for item in batch["results"]] == ["1", "2"], (
        "job.data must be saved before the raise, or the failed row loses its detail"
    )
    assert merge_calls == [], "a partial result must not be merged into main"


def test_batch_selected_sync_blocks_when_no_netbox_endpoint_is_enabled(
    monkeypatch, proxbox_sync_job_module
):
    """The batch path writes NetBox objects, so it obeys the same hard gate.

    Selected-object runs reach proxbox-api through ``sync_individual`` rather
    than the SSE stages, but the *writes* land in NetBox exactly the same way.
    Before this, the batch branch returned before the preflight entirely, so a
    NetBox that had disabled its own endpoint could still be written to using
    whatever credentials the backend happened to still hold — the one thing the
    disabled-endpoint gate exists to prevent.
    """
    module = proxbox_sync_job_module
    batch_calls: list[dict[str, object]] = []

    async def _fake_batch(*args, **kwargs):  # pragma: no cover - must not run
        batch_calls.append(kwargs)
        return {}

    monkeypatch.setattr(module, "_run_batch_selected_sync", _fake_batch)

    services_mod = types.ModuleType("netbox_proxbox.services")
    services_mod.run_sync_stream = lambda *args, **kwargs: ({"ok": True}, 200)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    # No enabled NetBoxEndpoint anywhere — this NetBox declines to be written to.
    monkeypatch.setattr(
        sys.modules["netbox_proxbox.models"].NetBoxEndpoint,
        "objects",
        SimpleNamespace(all=lambda: [], filter=lambda **kwargs: []),
    )

    job = module.ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job_batch_gate")
    job.job = MagicMock()
    job.job.data = None

    with pytest.raises(
        module.ProxboxPreflightError, match="no enabled NetBox endpoint"
    ):
        module.ProxboxSyncJob.run(
            job,
            sync_types=[module.SyncTypeChoices.ALL],
            batch_object_type="virtual-machine",
            batch_object_ids=["1", "2"],
        )

    assert batch_calls == [], "the batch must not run once the preflight blocks"


def test_batch_selected_sync_forwards_the_pinned_backend(
    monkeypatch, proxbox_sync_job_module
):
    """A job pinned to backend 7 must run its batch against backend 7."""
    module = proxbox_sync_job_module
    batch_calls: list[dict[str, object]] = []

    async def _fake_batch(*args, **kwargs):
        batch_calls.append(kwargs)
        return {
            "batch_object_type": kwargs["batch_object_type"],
            "batch_object_label": "Virtual Machine",
            "total": 1,
            "succeeded": 1,
            "failed": 0,
            "results": [],
        }

    monkeypatch.setattr(module, "_run_batch_selected_sync", _fake_batch)

    services_mod = types.ModuleType("netbox_proxbox.services")
    services_mod.run_sync_stream = lambda *args, **kwargs: ({"ok": True}, 200)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    job = module.ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job_batch_pin")
    job.job = MagicMock()
    job.job.data = None

    module.ProxboxSyncJob.run(
        job,
        sync_types=[module.SyncTypeChoices.ALL],
        batch_object_type="virtual-machine",
        batch_object_ids=["1"],
        fastapi_endpoint_id=7,
    )

    assert [call["fastapi_endpoint_id"] for call in batch_calls] == [7]


def _arrange_blocked_batch(monkeypatch, module, name):
    """Stub a selected-object run and record whether the batch ever started.

    Returns ``(job, batch_calls)``. The caller decides *why* the Proxmox scope
    fails to resolve; both reasons must stop the run in the same place.
    """
    batch_calls: list[dict[str, object]] = []

    async def _fake_batch(*args, **kwargs):  # pragma: no cover - must not run
        batch_calls.append(kwargs)
        return {}

    monkeypatch.setattr(module, "_run_batch_selected_sync", _fake_batch)

    services_mod = types.ModuleType("netbox_proxbox.services")
    services_mod.run_sync_stream = lambda *args, **kwargs: ({"ok": True}, 200)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    # Stale rows the backend still holds are exactly what makes an unscoped
    # request dangerous, so leave them present: the run must stop anyway.
    monkeypatch.setattr(
        sys.modules["netbox_proxbox.views.backend_sync"],
        "list_backend_proxmox_endpoints",
        lambda *a, **kw: ([{"id": 7, "name": "pve-stale (nb:7)"}], None),
    )

    job = module.ProxboxSyncJob()
    job.logger = logging.getLogger(name)
    job.job = MagicMock()
    job.job.data = None
    return job, batch_calls


def test_batch_selected_sync_blocks_when_no_proxmox_endpoint_is_enabled(
    monkeypatch, proxbox_sync_job_module
):
    """A selected-object run with no enabled Proxmox endpoint must not run.

    The batch path reaches proxbox-api through ``sync_individual()``, whose
    routes resolve their Proxmox sessions through the same dependency the SSE
    stages use — and that dependency treats an absent ``proxmox_endpoint_ids``
    as "use every endpoint I hold". So an unscoped selected-object sync is not a
    narrower request than a staged one, it is the *widest* request the backend
    accepts, reaching endpoints this NetBox has disabled. The staged path has
    refused this since the fail-loud endpoint-scope record; the batch path used
    to send it.
    """
    module = proxbox_sync_job_module
    job, batch_calls = _arrange_blocked_batch(
        monkeypatch, module, "test_proxbox_job_batch_scope_empty"
    )

    class _QS(list):
        def values_list(self, *args, **kwargs):
            return list(self)

    monkeypatch.setattr(
        sys.modules["netbox_proxbox.models"],
        "ProxmoxEndpoint",
        SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: _QS([]))),
    )

    with pytest.raises(
        module.ProxboxPreflightError, match="no enabled Proxmox endpoint"
    ) as excinfo:
        module.ProxboxSyncJob.run(
            job,
            sync_types=[module.SyncTypeChoices.ALL],
            batch_object_type="virtual-machine",
            batch_object_ids=["1", "2"],
        )

    assert "is not a fallback" in str(excinfo.value), (
        "the message must say why syncing unscoped is not the safe degradation"
    )
    assert batch_calls == [], "no proxbox-api call may be made without a scope"


def test_batch_selected_sync_blocks_when_no_endpoint_resolves_to_a_backend_id(
    monkeypatch, proxbox_sync_job_module
):
    """Enabled but unresolvable endpoints are the same refusal, not a fallback.

    An endpoint the backend does not hold under a matching connection target
    yields no wire id, so the scope would come out empty — and an empty scope is
    dropped from the request, which is the unscoped call again. Refuse instead.
    """
    module = proxbox_sync_job_module
    job, batch_calls = _arrange_blocked_batch(
        monkeypatch, module, "test_proxbox_job_batch_scope_unresolved"
    )
    monkeypatch.setattr(
        module.sync_stages,
        "_resolve_wire_endpoint_ids",
        lambda scopes, **kwargs: ({}, None),
    )

    with pytest.raises(
        module.ProxboxPreflightError, match="none of the enabled Proxmox endpoints"
    ):
        module.ProxboxSyncJob.run(
            job,
            sync_types=[module.SyncTypeChoices.ALL],
            batch_object_type="virtual-machine",
            batch_object_ids=["1", "2"],
        )

    assert batch_calls == [], "no proxbox-api call may be made without a scope"


def test_batch_wire_endpoint_scope_narrows_rather_than_failing_on_partial_drift(
    monkeypatch, proxbox_sync_job_module
):
    """One drifted endpoint narrows the scope; it does not fail the whole run.

    Failing outright because an *unrelated* endpoint drifted would be a
    regression, and the narrowed scope is still strictly safer than the unscoped
    request it replaces. The caller is handed the skipped pks so it can say so
    in the job log, and the resolved map so it can refuse — by name — exactly
    the objects that belong to a skipped endpoint.
    """
    ss = proxbox_sync_job_module.sync_stages
    monkeypatch.setattr(
        ss,
        "_resolve_wire_endpoint_ids",
        lambda scopes, **kwargs: ({"1": "11"}, None),
    )

    scope, skipped, error, wire_by_pk = ss._batch_wire_endpoint_scope(["1", "2"])

    assert (scope, skipped, error) == ("11", ["2"], None)
    assert wire_by_pk == {"1": "11"}, (
        "the per-object pin needs plugin pk → backend id, and the skipped "
        "endpoint must be absent rather than mapped to something else"
    )


def _arrange_batch_storage_sync(monkeypatch, module):
    """Stub the models a `proxmox-storage` batch run resolves, and record calls.

    Returns the list every `sync_individual_with_dependencies()` call appends
    its arguments to.
    """
    storage = SimpleNamespace(
        pk=5, name="local-lvm", cluster=SimpleNamespace(name="lab")
    )

    def _manager(rows):
        queryset = SimpleNamespace(filter=lambda **kwargs: rows)
        return SimpleNamespace(select_related=lambda *a, **kw: queryset)

    # `_run_batch_selected_sync` resolves its models lazily, at call time.
    virtualization_mod = types.ModuleType("virtualization")
    virtualization_models_mod = types.ModuleType("virtualization.models")
    virtualization_models_mod.VirtualMachine = SimpleNamespace(objects=_manager([]))
    virtualization_mod.models = virtualization_models_mod
    monkeypatch.setitem(sys.modules, "virtualization", virtualization_mod)
    monkeypatch.setitem(sys.modules, "virtualization.models", virtualization_models_mod)

    models_mod = types.ModuleType("netbox_proxbox.models")
    models_mod.ProxmoxStorage = SimpleNamespace(objects=_manager([storage]))
    models_mod.VMBackup = SimpleNamespace(objects=_manager([]))
    models_mod.VMSnapshot = SimpleNamespace(objects=_manager([]))
    models_mod.VMTaskHistory = SimpleNamespace(objects=_manager([]))
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_mod)

    calls: list[dict[str, object]] = []

    def _fake_sync(path, query_params=None, **kwargs):
        calls.append({"path": path, "query_params": dict(query_params or {}), **kwargs})
        return {"object_type": "storage", "action": "updated"}, 200, []

    individual_sync_mod = types.ModuleType("netbox_proxbox.services.individual_sync")
    individual_sync_mod.sync_individual_with_dependencies = _fake_sync
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.individual_sync", individual_sync_mod
    )

    monkeypatch.setattr(module, "_proxbox_fetch_max_concurrency_setting", lambda: 2)
    return calls


def _proxmox_cluster_objects(cluster_owners):
    """Stub `ProxmoxCluster.objects` for `_owner_endpoint_pks_by_cluster_id()`.

    ``cluster_owners`` maps a core ``virtualization.Cluster`` id to the list of
    ``ProxmoxEndpoint`` pks that claim it — one entry for the normal case, two
    for the ambiguous one. The **whole** claim set is what the helper returns,
    so an entry with two pks is what makes the tri-state distinguishable from
    an absent one.
    """

    class _QuerySet:
        def __init__(self, rows):
            self._rows = rows

        def exclude(self, **kwargs):
            return self

        def values_list(self, *fields, **kwargs):
            return self

        def distinct(self):
            return self

        def __iter__(self):
            return iter(self._rows)

    def _filter(**kwargs):
        wanted = set(kwargs.get("netbox_cluster_id__in") or ())
        return _QuerySet(
            [
                (cluster_id, endpoint_pk)
                for cluster_id, endpoint_pks in cluster_owners.items()
                if cluster_id in wanted
                for endpoint_pk in endpoint_pks
            ]
        )

    return SimpleNamespace(filter=_filter)


def _arrange_batch_duplicate_identifier_sync(monkeypatch, module, *, cluster_owners):
    """Two storages that are indistinguishable to proxbox-api, on two estates.

    Both are ``local-lvm`` on a cluster called ``cluster01``, so the two
    `sync/individual/storage` requests they produce are **byte-identical** apart
    from the endpoint scope. That is the whole point: Proxmox identifiers are
    unique per endpoint, not across the estate, so the scope is the only thing
    that can tell the backend which one to answer with.
    """

    def _manager(rows):
        queryset = SimpleNamespace(filter=lambda **kwargs: rows)
        return SimpleNamespace(select_related=lambda *a, **kw: queryset)

    storages = [
        SimpleNamespace(
            pk=5,
            name="local-lvm",
            cluster_id=41,
            cluster=SimpleNamespace(name="cluster01"),
        ),
        SimpleNamespace(
            pk=6,
            name="local-lvm",
            cluster_id=42,
            cluster=SimpleNamespace(name="cluster01"),
        ),
    ]

    virtualization_mod = types.ModuleType("virtualization")
    virtualization_models_mod = types.ModuleType("virtualization.models")
    virtualization_models_mod.VirtualMachine = SimpleNamespace(objects=_manager([]))
    virtualization_mod.models = virtualization_models_mod
    monkeypatch.setitem(sys.modules, "virtualization", virtualization_mod)
    monkeypatch.setitem(sys.modules, "virtualization.models", virtualization_models_mod)

    models_mod = types.ModuleType("netbox_proxbox.models")
    models_mod.ProxmoxStorage = SimpleNamespace(objects=_manager(storages))
    models_mod.VMBackup = SimpleNamespace(objects=_manager([]))
    models_mod.VMSnapshot = SimpleNamespace(objects=_manager([]))
    models_mod.VMTaskHistory = SimpleNamespace(objects=_manager([]))
    models_mod.ProxmoxCluster = SimpleNamespace(
        objects=_proxmox_cluster_objects(cluster_owners)
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_mod)

    calls: list[dict[str, object]] = []

    def _fake_sync(path, query_params=None, **kwargs):
        calls.append({"path": path, "query_params": dict(query_params or {}), **kwargs})
        return {"object_type": "storage", "action": "updated"}, 200, []

    individual_sync_mod = types.ModuleType("netbox_proxbox.services.individual_sync")
    individual_sync_mod.sync_individual_with_dependencies = _fake_sync
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.individual_sync", individual_sync_mod
    )

    monkeypatch.setattr(module, "_proxbox_fetch_max_concurrency_setting", lambda: 2)
    return calls


def test_batch_selected_sync_pins_each_object_to_its_own_endpoint(
    monkeypatch, proxbox_sync_job_module
):
    """The job-wide scope is not narrow enough when identifiers collide.

    ``cluster01/local-lvm`` exists on both estates, and the individual-sync
    route carries nothing else to tell them apart. Sent with the job-wide scope,
    *both* endpoints can answer and the backend takes whichever did — so one of
    these two NetBox rows gets the other estate's storage written into it, with
    no error anywhere. Each object therefore travels scoped to the single
    endpoint its own ``ProxmoxCluster`` names.
    """
    ss = proxbox_sync_job_module.sync_stages
    calls = _arrange_batch_duplicate_identifier_sync(
        monkeypatch, ss, cluster_owners={41: ["1"], 42: ["2"]}
    )

    result = asyncio.run(
        ss._run_batch_selected_sync(
            None,
            batch_object_type="proxmox-storage",
            batch_object_ids=["5", "6"],
            proxmox_wire_endpoint_ids="11,22",
            proxmox_wire_endpoint_by_pk={"1": "11", "2": "22"},
        )
    )

    assert result["succeeded"] == 2
    scopes = sorted(str(call["proxmox_endpoint_ids"]) for call in calls)
    assert scopes == ["11", "22"], (
        "each object must be asked of exactly its own endpoint, never of both"
    )
    assert sorted(
        str(call["query_params"]["proxmox_endpoint_ids"]) for call in calls
    ) == ["11", "22"], "the pin must reach the query params too, not just the argument"


def test_batch_selected_sync_refuses_an_object_whose_endpoint_was_skipped(
    monkeypatch, proxbox_sync_job_module
):
    """An object owned by a dropped endpoint is refused, not re-asked elsewhere.

    Endpoint 2 drifted and was skipped from the scope. Sending its object with
    the *remaining* scope is not a degraded sync — it is the wrong-estate write
    this pinning exists to prevent, because the identifiers it carries also
    exist on endpoint 1. Fail that one object by name and let the rest run.
    """
    ss = proxbox_sync_job_module.sync_stages
    calls = _arrange_batch_duplicate_identifier_sync(
        monkeypatch, ss, cluster_owners={41: ["1"], 42: ["2"]}
    )

    result = asyncio.run(
        ss._run_batch_selected_sync(
            None,
            batch_object_type="proxmox-storage",
            batch_object_ids=["5", "6"],
            proxmox_wire_endpoint_ids="11",
            proxmox_wire_endpoint_by_pk={"1": "11"},
        )
    )

    assert result["succeeded"] == 1
    assert [str(call["proxmox_endpoint_ids"]) for call in calls] == ["11"], (
        "the skipped endpoint's object must not be asked of the surviving one"
    )
    refused = [
        entry for entry in result["results"] if str(entry.get("object_id")) == "6"
    ]
    assert refused and refused[0]["status"] == 424
    assert "not in this run's endpoint scope" in refused[0]["error"]


def test_batch_selected_sync_falls_back_to_the_job_scope_for_an_unreflected_object(
    monkeypatch, proxbox_sync_job_module
):
    """No reflected ``ProxmoxCluster`` yet means *unknown owner*, not *no owner*.

    A first-ever sync is exactly the run that has nothing to resolve an owner
    from, and refusing there would make the object unsyncable forever. The
    job-wide scope is what this path sent before per-object pinning existed, so
    falling back to it cannot be a regression — it is the previous behaviour,
    kept for the one case pinning genuinely cannot answer.

    The scope here names **one** endpoint, which is the only shape the fallback
    still applies to: "the whole run" and "that one endpoint" are the same
    request, so nothing is being guessed. The multi-endpoint shape is the next
    test, and it refuses.
    """
    ss = proxbox_sync_job_module.sync_stages
    calls = _arrange_batch_duplicate_identifier_sync(monkeypatch, ss, cluster_owners={})

    result = asyncio.run(
        ss._run_batch_selected_sync(
            None,
            batch_object_type="proxmox-storage",
            batch_object_ids=["5", "6"],
            proxmox_wire_endpoint_ids="11",
            proxmox_wire_endpoint_by_pk={"1": "11"},
        )
    )

    assert result["succeeded"] == 2
    assert [str(call["proxmox_endpoint_ids"]) for call in calls] == ["11", "11"]


def test_batch_selected_sync_refuses_an_unreflected_object_across_two_endpoints(
    monkeypatch, proxbox_sync_job_module
):
    """Unknown ownership may widen to *one* endpoint — never to a set of them.

    The fallback above is justified by a first-ever sync on an install that has
    nothing reflected yet, and on that install the job scope names a single
    endpoint. Carrying the same fallback into a multi-endpoint run turns it back
    into the defect the per-object pinning closed: the request names only
    ``local-lvm`` on ``cluster01``, both estates hold one, both answer, and the
    backend writes whichever replied into this NetBox row with no error raised.

    "We could not determine the owner" is not a licence to ask everybody. It is
    also *recoverable* in a way a wrong write is not — a staged sync reflects
    the clusters, ownership resolves, and the retry pins — so this refuses and
    says how to make it resolvable. Both fixtures' objects are unreflected here,
    so nothing reaches proxbox-api at all.
    """
    ss = proxbox_sync_job_module.sync_stages
    calls = _arrange_batch_duplicate_identifier_sync(monkeypatch, ss, cluster_owners={})

    result = asyncio.run(
        ss._run_batch_selected_sync(
            None,
            batch_object_type="proxmox-storage",
            batch_object_ids=["5", "6"],
            proxmox_wire_endpoint_ids="11,22",
            proxmox_wire_endpoint_by_pk={"1": "11", "2": "22"},
        )
    )

    assert result["succeeded"] == 0
    assert result["failed"] == 2
    assert calls == [], (
        "an object whose owner cannot be determined must not be asked of every "
        "endpoint in the run — that is the wrong-estate write, not a fallback"
    )
    assert [entry["status"] for entry in result["results"]] == [424, 424]
    assert "spans 2 Proxmox endpoints" in result["results"][0]["error"]
    assert "single endpoint" in result["results"][0]["error"]


def test_batch_selected_sync_refuses_when_two_endpoints_claim_one_cluster(
    monkeypatch, proxbox_sync_job_module
):
    """Ambiguous ownership refuses the object; it does not widen back out.

    *Unknown* and *ambiguous* look alike and must not be treated alike. Nothing
    claiming a cluster means we cannot tell yet — a first-ever sync — so the
    job-wide scope is an honest guess. Two endpoints claiming it means the
    estate **provably has** the duplicated namespace this pinning exists to
    survive: asking both would send a request only a cluster/node/VMID
    distinguishes to two Proxmox installations that both answer it, and the
    backend would write whichever replied first into this NetBox row. That is
    the defect, not a degraded form of the fix. The unambiguous object in the
    same batch is still pinned and still syncs.
    """
    ss = proxbox_sync_job_module.sync_stages
    calls = _arrange_batch_duplicate_identifier_sync(
        monkeypatch, ss, cluster_owners={41: ["1", "2"], 42: ["2"]}
    )

    result = asyncio.run(
        ss._run_batch_selected_sync(
            None,
            batch_object_type="proxmox-storage",
            batch_object_ids=["5", "6"],
            proxmox_wire_endpoint_ids="11,22",
            proxmox_wire_endpoint_by_pk={"1": "11", "2": "22"},
        )
    )

    assert result["succeeded"] == 1
    assert [str(call["proxmox_endpoint_ids"]) for call in calls] == ["22"], (
        "the ambiguous object must not be asked of anyone, and the unambiguous "
        "one must still be pinned rather than dragged down with it"
    )
    refused = [
        entry for entry in result["results"] if str(entry.get("object_id")) == "5"
    ]
    assert refused and refused[0]["status"] == 424
    assert "claimed by more than one Proxmox endpoint (ids 1, 2)" in refused[0]["error"]


@pytest.mark.parametrize(
    "batch_object_type, obj, expected, why",
    [
        (
            "virtual-machine",
            SimpleNamespace(cluster_id=41),
            41,
            "a VM carries the core cluster directly",
        ),
        (
            "proxmox-storage",
            SimpleNamespace(cluster_id=41),
            41,
            "`ProxmoxStorage.cluster` FKs to `virtualization.Cluster`, not to "
            "`ProxmoxCluster` — so it is already the core id",
        ),
        (
            "vm-backup",
            SimpleNamespace(
                proxmox_storage=SimpleNamespace(cluster_id=41),
                virtual_machine=SimpleNamespace(cluster_id=42),
            ),
            41,
            "a backup's own sync parameters are built from its storage's "
            "cluster, so that is the endpoint the request actually names",
        ),
        (
            "vm-backup",
            SimpleNamespace(proxmox_storage=None, virtual_machine=None),
            None,
            "nothing to resolve an owner from",
        ),
        (
            "vm-snapshot",
            SimpleNamespace(
                virtual_machine=SimpleNamespace(cluster_id=42),
                proxmox_storage=SimpleNamespace(cluster_id=41),
            ),
            42,
            "a snapshot is addressed by its VM's cluster",
        ),
        (
            "vm-task-history",
            SimpleNamespace(virtual_machine=SimpleNamespace(cluster_id=42)),
            42,
            "a task-history row is addressed by its VM's cluster",
        ),
        (
            "virtual-machine",
            SimpleNamespace(cluster_id=None),
            None,
            "a VM with no cluster has no resolvable owner",
        ),
        (
            "unsupported",
            SimpleNamespace(cluster_id=41),
            None,
            "an unknown type resolves nothing rather than guessing",
        ),
    ],
)
def test_batch_object_core_cluster_id_contract(
    batch_object_type, obj, expected, why, proxbox_sync_job_module
):
    """All five batch types converge on a core cluster id, by different routes."""
    ss = proxbox_sync_job_module.sync_stages
    assert ss._batch_object_core_cluster_id(obj, batch_object_type) == expected, why


def test_run_batch_selected_sync_pins_each_object_call_to_that_backend(
    monkeypatch, proxbox_sync_job_module
):
    """`fastapi_endpoint_id` must reach every per-object `sync_individual` call.

    Each call resolves its own backend, so without the pin a multi-backend
    install validates one proxbox-api in the preflight and then syncs against
    whichever row happens to sort first.
    """
    ss = proxbox_sync_job_module.sync_stages
    calls = _arrange_batch_storage_sync(monkeypatch, ss)

    result = asyncio.run(
        ss._run_batch_selected_sync(
            None,
            batch_object_type="proxmox-storage",
            batch_object_ids=["5"],
            fastapi_endpoint_id=7,
        )
    )

    assert result["succeeded"] == 1
    assert calls == [
        {
            "path": "sync/individual/storage",
            "query_params": {"cluster_name": "lab", "storage_name": "local-lvm"},
            "netbox_branch_schema_id": None,
            "fastapi_endpoint_id": 7,
            "proxmox_endpoint_ids": None,
        }
    ]


def test_run_batch_selected_sync_passes_the_branch_schema_to_dependency_syncs(
    monkeypatch, proxbox_sync_job_module
):
    """A branch-scoped batch sync must pass the schema id as an *argument*.

    `sync_individual_with_dependencies()` forwards its `netbox_branch_schema_id`
    argument to every recursive dependency call, while `_sync_dependency()`
    rebuilds its params dict from scratch out of `_CONTEXT_KEYS` — which does
    not include the branch key. Putting the id only on `query_params` therefore
    wrote the selected object into the branch and every dependency resolved off
    it into the **main** schema.
    """
    ss = proxbox_sync_job_module.sync_stages
    calls = _arrange_batch_storage_sync(monkeypatch, ss)

    result = asyncio.run(
        ss._run_batch_selected_sync(
            None,
            batch_object_type="proxmox-storage",
            batch_object_ids=["5"],
            netbox_branch_schema_id="42",
        )
    )

    assert result["succeeded"] == 1
    assert calls == [
        {
            "path": "sync/individual/storage",
            "query_params": {
                "cluster_name": "lab",
                "storage_name": "local-lvm",
                "netbox_branch_schema_id": "42",
            },
            "netbox_branch_schema_id": "42",
            "fastapi_endpoint_id": None,
            "proxmox_endpoint_ids": None,
        }
    ]


def test_run_batch_selected_sync_passes_the_proxmox_scope_to_dependency_syncs(
    monkeypatch, proxbox_sync_job_module
):
    """The resolved Proxmox scope travels as an *argument*, not only a param.

    Same failure mode as the branch schema, and for a worse reason: dropping
    the scope does not narrow the request, it *widens* it. Every individual-sync
    route resolves its Proxmox sessions through the dependency that reads a
    missing ``proxmox_endpoint_ids`` as "use every endpoint I hold", so a scope
    that reached the selected object but was rebuilt away by `_sync_dependency()`
    would sync the object from the right endpoint and everything resolved off it
    from *all* of them — including endpoints disabled in this NetBox.

    The scope is a *single* endpoint because this fixture reflects no owning
    cluster: an unresolvable owner in a run spanning two or more endpoints is
    refused before any request is built, which would leave nothing to assert
    forwarding against. Forwarding is the subject here; the refusal has its own
    test.
    """
    ss = proxbox_sync_job_module.sync_stages
    calls = _arrange_batch_storage_sync(monkeypatch, ss)

    result = asyncio.run(
        ss._run_batch_selected_sync(
            None,
            batch_object_type="proxmox-storage",
            batch_object_ids=["5"],
            proxmox_wire_endpoint_ids="3",
        )
    )

    assert result["succeeded"] == 1
    assert calls == [
        {
            "path": "sync/individual/storage",
            "query_params": {
                "cluster_name": "lab",
                "storage_name": "local-lvm",
                "proxmox_endpoint_ids": "3",
            },
            "netbox_branch_schema_id": None,
            "fastapi_endpoint_id": None,
            "proxmox_endpoint_ids": "3",
        }
    ]


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
    # Overwrite flags resolve by plugin pk ("1"); the wire id is the translated
    # backend database id ("100"). Stub the translation (pk -> pk+"00").
    monkeypatch.setattr(
        proxbox_sync_job_module.sync_stages,
        "_resolve_wire_endpoint_ids",
        lambda scopes, **kwargs: (
            {scope[0]: scope[0] + "00" for scope in scopes if scope},
            None,
        ),
    )

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job_endpoint_overrides")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(job, sync_types=[st.ALL], proxmox_endpoint_ids=["1"])

    assert captured
    assert {query["proxmox_endpoint_ids"] for query in captured} == {"100"}
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
    # Overwrite flags resolve by plugin pk ("1"/"2"); the wire ids are the
    # translated backend database ids ("100"/"200"). Stub the translation.
    monkeypatch.setattr(
        proxbox_sync_job_module.sync_stages,
        "_resolve_wire_endpoint_ids",
        lambda scopes, **kwargs: (
            {scope[0]: scope[0] + "00" for scope in scopes if scope},
            None,
        ),
    )

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job_multi_endpoint_overrides")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    ProxboxSyncJob.run(job, sync_types=[st.DEVICES], proxmox_endpoint_ids=["1", "2"])

    assert [query["proxmox_endpoint_ids"] for query in captured] == ["100", "200"]
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


def test_build_base_query_params_separates_plugin_and_wire_ids(
    monkeypatch, proxbox_sync_job_module
):
    """Overwrite flags resolve by plugin pk; the wire carries the backend id."""
    sync_stages = proxbox_sync_job_module.sync_stages
    seen_ids: list[object] = []

    def effective_overwrites_for_endpoint(endpoint_id):
        seen_ids.append(endpoint_id)
        return {}

    monkeypatch.setattr(
        sync_stages,
        "effective_overwrites_for_endpoint",
        effective_overwrites_for_endpoint,
    )
    monkeypatch.setattr(
        sync_stages, "effective_sync_modes_for_endpoint", lambda _endpoint_id: {}
    )

    base_query = sync_stages._build_base_query_params(
        ["1"], None, wire_proxmox_endpoint_ids=["100"]
    )

    # Plugin pk "1" drove the per-endpoint overwrite resolution...
    assert seen_ids == ["1"]
    # ...but the backend database id "100" is what goes on the wire.
    assert base_query["proxmox_endpoint_ids"] == "100"


def test_build_base_query_params_defaults_wire_ids_to_plugin_ids(
    monkeypatch, proxbox_sync_job_module
):
    """Legacy single-id-space callers (no wire ids) keep the old behavior."""
    sync_stages = proxbox_sync_job_module.sync_stages
    monkeypatch.setattr(sync_stages, "effective_overwrites_for_endpoint", lambda _e: {})
    monkeypatch.setattr(sync_stages, "effective_sync_modes_for_endpoint", lambda _e: {})

    base_query = sync_stages._build_base_query_params(["1"], None)
    assert base_query["proxmox_endpoint_ids"] == "1"


def test_proxmox_endpoint_scopes_excludes_disabled_endpoints(
    monkeypatch, proxbox_sync_job_module
):
    """Disabled Proxmox endpoints must not appear in the default sync scopes."""
    sync_stages = proxbox_sync_job_module.sync_stages
    captured_filter: dict[str, object] = {}

    class _QS(list):
        def values_list(self, *args, **kwargs):
            return list(self)

    class _Manager:
        def filter(self, **kwargs):
            captured_filter.update(kwargs)
            # Only the enabled endpoint (pk 1) is returned; pk 2 is disabled.
            return _QS([1])

    models_mod = sys.modules["netbox_proxbox.models"]
    monkeypatch.setattr(
        models_mod, "ProxmoxEndpoint", SimpleNamespace(objects=_Manager())
    )

    scopes = sync_stages._proxmox_endpoint_scopes(None)

    assert captured_filter == {"enabled": True}
    assert scopes == [["1"]]


def test_proxmox_endpoint_scopes_returns_no_scope_when_every_endpoint_disabled(
    monkeypatch, proxbox_sync_job_module
):
    """Zero enabled endpoints means *no scope*, never the empty scope.

    An empty scope reaches the backend as a request carrying no
    ``proxmox_endpoint_ids`` at all, which proxbox-api reads as "sync every
    endpoint you hold". Disabling the last ProxmoxEndpoint would then have
    *widened* the sync to whatever the backend still had registered.
    """
    sync_stages = proxbox_sync_job_module.sync_stages

    class _QS(list):
        def values_list(self, *args, **kwargs):
            return list(self)

    models_mod = sys.modules["netbox_proxbox.models"]
    monkeypatch.setattr(
        models_mod,
        "ProxmoxEndpoint",
        SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: _QS([]))),
    )

    assert sync_stages._proxmox_endpoint_scopes(None) == []


def test_run_all_stages_fails_loud_when_no_proxmox_endpoint_is_enabled(
    monkeypatch, proxbox_sync_job_module
):
    """No enabled Proxmox endpoint fails the run instead of syncing everything.

    Stale rows on proxbox-api are what make the unscoped request dangerous, so
    the stub keeps them present: the run must still stop, and it must never
    reach the SSE transport.
    """
    sync_stages = proxbox_sync_job_module.sync_stages
    streamed: list[object] = []

    class _QS(list):
        def values_list(self, *args, **kwargs):
            return list(self)

    models_mod = sys.modules["netbox_proxbox.models"]
    monkeypatch.setattr(
        models_mod,
        "ProxmoxEndpoint",
        SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: _QS([]))),
    )
    monkeypatch.setattr(
        sys.modules["netbox_proxbox.views.backend_sync"],
        "list_backend_proxmox_endpoints",
        lambda *a, **kw: ([{"id": 7, "name": "pve-stale (nb:7)"}], None),
    )
    monkeypatch.setattr(
        sync_stages,
        "_execute_stage_sync",
        lambda *a, **kw: streamed.append((a, kw)),
    )

    job, records = _preflight_job()
    stages_out = sync_stages._run_all_stages_sync(
        job=job,
        stages=["devices"],
        params={},
        run_started=0.0,
    )

    assert streamed == [], "a disabled estate must never reach the backend stream"
    assert len(stages_out) == 1
    record = stages_out[0]
    assert record["sync_type"] == "endpoint-scope"
    assert record["endpoint_id"] is None
    assert record["result_summary"]["ok"] is False
    assert "no enabled Proxmox endpoint" in record["result_summary"]["error"]
    assert "is not a fallback" in record["result_summary"]["error"], (
        "the message must say why syncing unscoped is not the safe degradation"
    )
    assert any("Skipping SSE sync entirely" in entry for entry in records["error"])


def _run_with_unresolvable_endpoints(
    monkeypatch,
    proxbox_sync_job_module,
    *,
    endpoint_ids,
    resolvable,
    sync_modes=None,
    expect_error=True,
):
    """Run a sync where only ``resolvable`` endpoint pks have a backend id.

    ``sync_modes`` seeds ``effective_sync_modes_for_endpoint`` so a caller can
    make the selected stages mode-disabled; ``expect_error=False`` then runs the
    job to completion instead of asserting it raises.
    """
    captured: list[dict[str, object]] = []
    services_mod = types.ModuleType("netbox_proxbox.services")

    def run_sync_stream(path, query_params=None, **stream_kwargs):
        captured.append(dict(query_params or {}))
        return ({"stream": True, "response": {"ok": True}}, 200)

    services_mod.run_sync_stream = run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    monkeypatch.setattr(
        proxbox_sync_job_module.sync_stages,
        "effective_overwrites_for_endpoint",
        lambda _endpoint_id: {},
    )
    # Patch the resolver on **both** modules.  `_sync_stage_settings()` copies
    # jobs.py's own imported reference onto `sync_stages` on every run, so a
    # patch applied only to `sync_stages` is silently reverted before the stage
    # loop reads it — the run then uses the real global sync modes and the
    # mode-disabled case never triggers.
    resolve_modes = lambda _endpoint_id: dict(sync_modes or {})  # noqa: E731
    for _module in (proxbox_sync_job_module, proxbox_sync_job_module.sync_stages):
        monkeypatch.setattr(_module, "effective_sync_modes_for_endpoint", resolve_modes)
    # `_set_sync_mode_vars` writes module globals; pin them through monkeypatch
    # so a mode-disabled run cannot leak into the next test in this file.
    for _field in proxbox_sync_job_module.sync_stages.SYNC_MODE_FIELDS:
        monkeypatch.setattr(
            proxbox_sync_job_module.sync_stages,
            _field,
            getattr(proxbox_sync_job_module.sync_stages, _field, None),
            raising=False,
        )
    # Only the listed pks translate to a backend id (fail-loud path for the rest).
    monkeypatch.setattr(
        proxbox_sync_job_module.sync_stages,
        "_resolve_wire_endpoint_ids",
        lambda scopes, **kwargs: (
            {pk: pk + "00" for pk in resolvable},
            "endpoint not registered on backend",
        ),
    )

    ProxboxSyncJob = proxbox_sync_job_module.ProxboxSyncJob
    job = ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job_skip_unresolved")
    job.job = MagicMock()
    job.job.data = None

    st = proxbox_sync_job_module.SyncTypeChoices
    if not expect_error:
        ProxboxSyncJob.run(
            job, sync_types=[st.DEVICES], proxmox_endpoint_ids=endpoint_ids
        )
        return job, captured, ""
    with pytest.raises(RuntimeError) as excinfo:
        ProxboxSyncJob.run(
            job, sync_types=[st.DEVICES], proxmox_endpoint_ids=endpoint_ids
        )
    return job, captured, str(excinfo.value)


def test_run_all_stages_skips_endpoint_that_does_not_resolve(
    monkeypatch, proxbox_sync_job_module
):
    """When a plugin endpoint has no backend id, its stages must NOT run.

    And because nothing at all was synced, the job must end **errored** rather
    than reporting success over an empty run — the silent no-op that made the
    original report so hard to diagnose.
    """
    job, captured, message = _run_with_unresolvable_endpoints(
        monkeypatch, proxbox_sync_job_module, endpoint_ids=["1"], resolvable=()
    )

    # No SSE stage ran (we never sync an unresolved endpoint unscoped).
    assert captured == []
    assert "No sync stage ran" in message
    assert "endpoint not registered on backend" in message, (
        "the per-endpoint reason must reach the job error, not just the log"
    )

    # The partial results are still persisted before the raise, so the operator
    # can see which endpoint failed and why.
    stages = job.job.data["proxbox_sync"]["response"]["stages"]
    scope_errors = [
        stage
        for stage in stages
        if stage.get("sync_type") == "endpoint-scope"
        and not stage["result_summary"].get("ok", True)
    ]
    assert scope_errors, "expected a fail-loud endpoint-scope error stage"


def test_run_fails_when_only_some_endpoints_resolve(
    monkeypatch, proxbox_sync_job_module
):
    """A partial skip is still a failure — but says so differently.

    The endpoints that did resolve are synced first and their results saved;
    only then does the job report the ones that never ran.
    """
    _job, captured, message = _run_with_unresolvable_endpoints(
        monkeypatch,
        proxbox_sync_job_module,
        endpoint_ids=["1", "2"],
        resolvable=("1",),
    )

    assert captured, "the resolvable endpoint must still have been synced"
    assert "1 Proxmox endpoint(s) were skipped" in message
    assert "endpoint 2" in message
    assert "No sync stage ran" not in message


def test_unresolved_endpoint_with_every_stage_mode_disabled_is_a_skip_not_a_failure(
    monkeypatch, proxbox_sync_job_module
):
    """Nothing was lost, so nothing is wrong — record skips, do not hard-fail.

    Wire-id resolution happens *before* the stage loop, and the stage loop is
    where sync modes are normally applied. So an endpoint that is not registered
    on the backend used to fail loudly even when every selected stage was
    disabled by its sync modes — a run that would have synced exactly zero
    objects anyway reported "No sync stage ran" and sent the operator off to
    debug backend registration for a no-op.
    """
    job, captured, _message = _run_with_unresolvable_endpoints(
        monkeypatch,
        proxbox_sync_job_module,
        endpoint_ids=["1"],
        resolvable=(),
        # `devices` resolves to the `node` resource; disabling it disables the
        # only stage this run selects.
        sync_modes={"sync_mode_node": "disabled"},
        expect_error=False,
    )

    # Still nothing synced — the endpoint has no wire id, so no stage may run.
    assert captured == []

    stages = job.job.data["proxbox_sync"]["response"]["stages"]
    assert [stage["sync_type"] for stage in stages] == ["devices"]
    summary = stages[0]["result_summary"]
    assert summary["ok"] is True
    assert summary["skipped"] is True
    assert "sync_mode_node=disabled" in summary["reason"]
    # ...and specifically NOT the fail-loud endpoint-scope stage.
    assert not [s for s in stages if s.get("sync_type") == "endpoint-scope"]


# ── preflight: blocking vs non-blocking outcomes ─────────────────────────────
#
# Pushing the NetBox endpoint is the only thing that gives proxbox-api the
# credentials it writes NetBox objects with. When that push failed the preflight
# used to log a warning and continue, so the run marched into stages that could
# not possibly succeed and reported whichever downstream symptom surfaced first
# (in the field: "Error ensuring Proxbox tag", minutes later, on a different
# stage). It now fails at the preflight — but only when the backend *confirms*
# it holds no NetBox endpoint, never on an ambiguous signal.


THIS_NETBOX_DOMAIN = "netbox.example.test"
# A stored backend row that provably points at *this* NetBox: same host, same
# port. Anything else is somebody else's NetBox, however plausible it looks.
BACKEND_ROW_THIS_NETBOX = {
    "id": 1,
    "name": "whatever-the-backend-called-it",
    "domain": THIS_NETBOX_DOMAIN,
    "ip_address": "127.0.0.1",
    "port": 443,
    # `NetBoxEndpointResponse` declares both of these required, and the fallback
    # compares them: identity proves the row is ours, these prove it is current.
    "verify_ssl": True,
    "token_version": "v1",
}


def _preflight_context():
    return SimpleNamespace(
        http_url="http://backend:8800",
        headers={"X-Proxbox-API-Key": "stub"},
        verify_ssl=True,
    )


def _preflight_job():
    records = {"info": [], "warning": [], "error": []}
    job = SimpleNamespace(
        logger=SimpleNamespace(
            info=lambda msg: records["info"].append(str(msg)),
            warning=lambda msg: records["warning"].append(str(msg)),
            error=lambda msg: records["error"].append(str(msg)),
        )
    )
    return job, records


def _arrange_preflight(
    monkeypatch,
    *,
    netbox_rows=(1,),
    push_ok=True,
    backend_list=([{"id": 1}], None),
    netbox_ip=None,
    netbox_domain=THIS_NETBOX_DOMAIN,
    netbox_verify_ssl=True,
    netbox_token_version="v1",
    netbox_token_value="nbt-the-token-this-netbox-carries-now",
    netbox_fingerprint="current",
):
    """Point the stubbed modules at one specific preflight scenario.

    ``netbox_fingerprint`` selects what the row's locally recorded
    last-successful-push fingerprint says about the *secret*, which is the one
    thing ``NetBoxEndpointResponse`` cannot report:

    * ``"current"`` — recorded by a push of the credentials the row carries now,
      so a failed refresh is genuinely transient (warn and continue);
    * ``"stale"`` — recorded before an in-place token rotation, so the backend
      holds a credential this NetBox has replaced (block);
    * ``"absent"`` — never recorded, which is the pre-upgrade state and reads the
      same way as stale, because fail-closed is the only safe default here.
    """
    monkeypatch.setattr(
        sys.modules["netbox_proxbox.services.backend_context"],
        "get_fastapi_request_context",
        lambda **kwargs: _preflight_context(),
    )

    # Rows carry a real connection identity (domain + port). That is what
    # `backend_holds_netbox_endpoint()` matches on — the NetBox endpoint is a
    # singleton on proxbox-api, overwritten by position, so a row's *presence*
    # says nothing about whose credentials it holds.
    # `ip_address` is left unset by default: that is the common domain-only
    # deployment, and the one where the push payload substitutes a synthetic
    # `127.0.0.1` the identity check must refuse to treat as evidence.
    rows = [
        SimpleNamespace(
            pk=pk,
            name=f"netbox-{pk}",
            domain=netbox_domain,
            ip_address=(
                SimpleNamespace(address=netbox_ip) if netbox_ip is not None else None
            ),
            port=443,
            # The two pushed fields the backend also returns. Identity settles
            # *whose* row it is; these settle whether it still describes the
            # trust configuration this NetBox declares.
            verify_ssl=netbox_verify_ssl,
            effective_token_version=netbox_token_version,
            effective_token_value=netbox_token_value,
            pushed_credential_fingerprint="",
        )
        for pk in netbox_rows
    ]

    # Fingerprints are produced by the **real** helper, never re-derived here —
    # a hand-rolled HMAC would stop tracking the code the moment the material or
    # the salt changed, and the tests would keep passing while it did.
    _real_backend_sync = load_real_backend_sync()
    for row in rows:
        if netbox_fingerprint == "current":
            row.pushed_credential_fingerprint = (
                _real_backend_sync.netbox_endpoint_credential_fingerprint(row)
            )
        elif netbox_fingerprint == "stale":
            # What the *previous* token would have recorded. Same row, same
            # domain/port/scheme — only the secret moved, which is exactly the
            # rotation `backend_holds_netbox_endpoint()` structurally cannot see.
            previous = SimpleNamespace(
                **{
                    **vars(row),
                    "effective_token_value": "nbt-the-token-that-was-rotated-away",
                }
            )
            row.pushed_credential_fingerprint = (
                _real_backend_sync.netbox_endpoint_credential_fingerprint(previous)
            )
        elif netbox_fingerprint != "absent":  # pragma: no cover - test-authoring guard
            raise ValueError(f"unknown netbox_fingerprint: {netbox_fingerprint!r}")

    monkeypatch.setattr(
        sys.modules["netbox_proxbox.models"].NetBoxEndpoint,
        "objects",
        SimpleNamespace(all=lambda: rows, filter=lambda **kwargs: rows),
        raising=False,
    )

    backend_sync = sys.modules["netbox_proxbox.views.backend_sync"]
    monkeypatch.setattr(
        backend_sync,
        "sync_netbox_endpoint_to_backend",
        lambda *a, **kw: (
            (True, None, None)
            if push_ok
            else (False, "Read timed out. (read timeout=10)", None)
        ),
    )
    monkeypatch.setattr(
        backend_sync, "list_backend_netbox_endpoints", lambda *a, **kw: backend_list
    )


def test_preflight_blocks_when_backend_holds_no_netbox_endpoint(
    monkeypatch, proxbox_sync_job_module
):
    """Push failed AND the backend definitively has none — nothing can succeed."""
    _arrange_preflight(monkeypatch, push_ok=False, backend_list=([], None))
    job, records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error, "this is the one case that must stop the run"
    assert "no NetBox endpoint" in result.blocking_error
    assert "http://backend:8800" in result.blocking_error, (
        "the operator needs to know which backend to go look at"
    )
    assert any("no NetBox endpoint" in entry for entry in records["error"])
    assert result.phases == [], "the Proxmox push loop must not run after blocking"


def test_preflight_continues_when_backend_already_holds_an_endpoint(
    monkeypatch, proxbox_sync_job_module
):
    """The backend may hold a usable record from an earlier push — not fatal.

    "Usable" means it provably points at *this* NetBox: same host, same port,
    in the one position the backend dials. Then a failed push is a transient
    refresh failure and the stored (possibly stale) credentials are still ours.
    """
    _arrange_preflight(
        monkeypatch,
        push_ok=False,
        backend_list=([BACKEND_ROW_THIS_NETBOX], None),
    )
    job, records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error is None
    assert result.hint and "was not pushed" in result.hint
    assert any("may" in entry and "stale" in entry for entry in records["warning"])


def test_preflight_blocks_when_only_a_later_backend_row_is_ours(
    monkeypatch, proxbox_sync_job_module
):
    """Our row behind somebody else's is not our row — position is the contract.

    The NetBox endpoint on proxbox-api is a **positional** singleton: the push
    overwrites entry ``[0]``, and entry ``[0]`` is what the backend dials. A
    listing that returns more than one row means that contract no longer
    describes the backend, and the response says nothing about which row wins.

    Accepting a match found further down is the failure this blocks. Scanning
    the whole list looks *more* thorough and is strictly less safe: it reports
    "the backend already holds us, continue" on the strength of a row at index
    1, while the record at index 0 — here a foreign one — is what actually
    authenticates the sync. The run would then write this estate's Proxmox
    inventory using another NetBox's credentials, which is precisely what
    identity checking exists to stop; the extra row just reaches it by counting
    instead of by comparing. Unknown fails closed.
    """
    _arrange_preflight(
        monkeypatch,
        push_ok=False,
        backend_list=([{"id": 7}, BACKEND_ROW_THIS_NETBOX], None),
    )
    job, records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error is not None
    assert "do not point at this NetBox" in result.blocking_error
    assert not any(
        "may" in entry and "stale" in entry for entry in records["warning"]
    ), (
        "a row we cannot prove the backend dials must not produce the "
        "'continuing on stored configuration' warning"
    )


def test_preflight_blocks_when_stored_endpoint_points_at_a_different_netbox(
    monkeypatch, proxbox_sync_job_module
):
    """Rows exist, but none is *ours* — worse than an empty backend, not better.

    proxbox-api stores the NetBox endpoint as a **singleton**: every push
    overwrites entry ``[0]`` by position, never matching by name. So a row being
    present proves only that *somebody* pushed one. If our own push just failed
    and the row that is there points somewhere else, continuing would let the
    backend keep writing with credentials for a different NetBox instance —
    silently reflecting this estate's Proxmox data into someone else's database.
    Fail closed.
    """
    _arrange_preflight(
        monkeypatch,
        push_ok=False,
        backend_list=(
            [
                {
                    "id": 1,
                    "name": "netbox-1",  # same *name* as our row — deliberately
                    "domain": "someone-elses-netbox.example.test",
                    "ip_address": "10.9.9.9",
                    "port": 443,
                }
            ],
            None,
        ),
    )
    job, records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error, "an unmatched row must not be treated as ours"
    assert "do not point at this NetBox" in result.blocking_error
    assert "http://backend:8800" in result.blocking_error
    assert any("do not point at this NetBox" in entry for entry in records["error"])
    assert result.phases == [], "the Proxmox push loop must not run after blocking"


def test_preflight_blocks_when_stored_endpoint_uses_a_different_port(
    monkeypatch, proxbox_sync_job_module
):
    """Same host, different port is a different service — not our NetBox."""
    _arrange_preflight(
        monkeypatch,
        push_ok=False,
        backend_list=([{**BACKEND_ROW_THIS_NETBOX, "port": 8443}], None),
    )
    job, _records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error
    assert "do not point at this NetBox" in result.blocking_error


def test_preflight_blocks_when_another_domain_only_netbox_shares_the_loopback_ip(
    monkeypatch, proxbox_sync_job_module
):
    """The synthetic ``127.0.0.1`` fallback is not identity evidence.

    ``_netbox_endpoint_backend_payload()`` substitutes ``127.0.0.1`` whenever the
    local row has no linked IP, so the backend still has something to dial. That
    makes loopback the *most common* stored value, not a distinguishing one:
    every domain-only NetBox pushes it. Matching on it would let any two
    domain-only instances sharing a backend identify as each other on the
    fallback alone — the exact cross-instance write this check exists to block,
    reached through a field neither operator ever configured. Only an explicitly
    configured IP counts, so here the mismatched domain is the whole answer.
    """
    _arrange_preflight(
        monkeypatch,
        push_ok=False,
        backend_list=(
            [
                {
                    "id": 1,
                    "name": "NetBox Endpoint",
                    "domain": "someone-elses-netbox.example.test",
                    "ip_address": "127.0.0.1",  # same synthetic fallback we send
                    "port": 443,
                }
            ],
            None,
        ),
    )
    job, records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error, "loopback is a fallback, not an identity"
    assert "do not point at this NetBox" in result.blocking_error
    assert any("do not point at this NetBox" in entry for entry in records["error"])


def test_preflight_blocks_when_a_different_domain_shares_our_configured_ip(
    monkeypatch, proxbox_sync_job_module
):
    """A shared address is not a shared identity.

    Two NetBox instances can sit behind one address as separate vhosts. The
    backend resolves ``host = domain if domain else ip_address``, so this stored
    row dials *their* vhost — our IP appearing in a field nobody reads is not
    evidence of anything.
    """
    _arrange_preflight(
        monkeypatch,
        push_ok=False,
        netbox_ip="10.0.30.207/24",
        backend_list=(
            [
                {
                    "id": 1,
                    "domain": "someone-elses-netbox.example.test",
                    "ip_address": "10.0.30.207",  # genuinely ours…
                    "port": 443,
                }
            ],
            None,
        ),
    )
    job, _records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error, "…but the domain says it is somebody else's"
    assert "do not point at this NetBox" in result.blocking_error


def test_preflight_blocks_when_the_stored_row_is_reached_by_address_not_by_name(
    monkeypatch, proxbox_sync_job_module
):
    """A blank stored ``domain`` is data, not a gap.

    We are configured with a domain, so proxbox-api would reach us at
    ``https://netbox.example.test:443``. The stored row names no domain, so the
    backend reaches *it* at ``https://10.0.30.207:443`` — a different service,
    which merely happens to sit at an address we also list. Reading the blank
    field as "not a conflict" and matching on the IP alone let that row certify
    a push of this estate's Proxmox inventory into whatever answers there.
    """
    _arrange_preflight(
        monkeypatch,
        push_ok=False,
        netbox_ip="10.0.30.207/24",
        backend_list=(
            [{"id": 1, "domain": "", "ip_address": "10.0.30.207", "port": 443}],
            None,
        ),
    )
    job, records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error, "the backend would dial an address, not our name"
    assert "do not point at this NetBox" in result.blocking_error
    assert any("do not point at this NetBox" in entry for entry in records["error"])


def test_preflight_continues_when_an_ip_only_netbox_matches_the_stored_address(
    monkeypatch, proxbox_sync_job_module
):
    """The same stored row *is* ours once we are the NetBox reached by address.

    Identity is the connection target, so the verdict has to follow what the
    backend would actually dial — not which of the two fields happens to be
    filled in. With no domain configured here, the address is the target, and
    the row that blocks the test above is the same row that matches this one.
    """
    _arrange_preflight(
        monkeypatch,
        push_ok=False,
        netbox_domain="",
        netbox_ip="10.0.30.207/24",
        backend_list=(
            [
                {
                    "id": 1,
                    "domain": "",
                    "ip_address": "10.0.30.207",
                    "port": 443,
                    "verify_ssl": True,
                    "token_version": "v1",
                }
            ],
            None,
        ),
    )
    job, records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error is None
    assert any("may" in entry and "stale" in entry for entry in records["warning"])


def test_preflight_continues_when_our_domain_matches_but_the_stored_ip_is_stale(
    monkeypatch, proxbox_sync_job_module
):
    """Once a domain is set, the stored address is a field nobody reads.

    proxbox-api resolves ``host = domain if domain else ip_address``, so a
    record of ours whose IP has since changed still dials exactly this NetBox.
    Demanding that every field agree would block a run that is provably safe,
    on a disagreement that cannot affect where the credentials go.
    """
    _arrange_preflight(
        monkeypatch,
        push_ok=False,
        netbox_ip="10.0.30.207/24",
        backend_list=(
            [
                {
                    "id": 1,
                    "domain": THIS_NETBOX_DOMAIN,
                    "ip_address": "192.0.2.9",  # the old address, never dialled
                    "port": 443,
                    "verify_ssl": True,
                    "token_version": "v1",
                }
            ],
            None,
        ),
    )
    job, records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error is None
    assert any("may" in entry and "stale" in entry for entry in records["warning"])


def test_preflight_blocks_when_the_stored_row_reports_no_port(
    monkeypatch, proxbox_sync_job_module
):
    """A row that names no port identifies no service.

    proxbox-api declares ``port`` as a required field on its NetBox-endpoint
    response, so every row it lists carries one. A row without it is not
    something this backend produced, and a port we cannot read is a target we
    cannot compare — either way, not provably ours.
    """
    _arrange_preflight(
        monkeypatch,
        push_ok=False,
        backend_list=(
            [{"id": 1, "domain": THIS_NETBOX_DOMAIN, "ip_address": "127.0.0.1"}],
            None,
        ),
    )
    job, _records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error
    assert "do not point at this NetBox" in result.blocking_error


def test_preflight_blocks_when_the_stored_row_has_a_superseded_tls_posture(
    monkeypatch, proxbox_sync_job_module
):
    """Our own row, our own target — and a security posture we already replaced.

    This is the case identity alone cannot see. The operator turned certificate
    verification back on, and the push carrying that change is exactly the one
    that failed, so proxbox-api is still holding ``verify_ssl=False``. Matching
    on host and port would call that a *transient refresh failure over our own
    credentials* and continue — with the backend writing to this NetBox over the
    unverified connection the operator had just decided was no longer acceptable.
    """
    _arrange_preflight(
        monkeypatch,
        push_ok=False,
        netbox_verify_ssl=True,
        backend_list=([{**BACKEND_ROW_THIS_NETBOX, "verify_ssl": False}], None),
    )
    job, records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error, "a superseded trust posture is not 'still ours'"
    assert "do not point at this NetBox" in result.blocking_error
    assert any("do not point at this NetBox" in entry for entry in records["error"])


def test_preflight_blocks_when_the_stored_row_holds_a_superseded_token_scheme(
    monkeypatch, proxbox_sync_job_module
):
    """A rotated token scheme is drift, not staleness we can shrug at.

    The stored row still names this NetBox, so it is ours — but it says the
    backend authenticates with a ``v1`` token while this NetBox has moved to
    ``v2``. Continuing would keep proxbox-api writing under the scheme the
    rotation was meant to retire.
    """
    _arrange_preflight(
        monkeypatch,
        push_ok=False,
        netbox_token_version="v2",
        backend_list=([{**BACKEND_ROW_THIS_NETBOX, "token_version": "v1"}], None),
    )
    job, _records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error
    assert "do not point at this NetBox" in result.blocking_error


def test_preflight_blocks_when_the_stored_row_omits_a_mandatory_trust_field(
    monkeypatch, proxbox_sync_job_module
):
    """Absent reads as drifted, and the asymmetry with the Proxmox side is on purpose.

    ``_proxmox_row_is_current()`` returning ``False`` costs one extra push. Here
    a ``False`` *blocks the run*, so the bar is what the backend guarantees:
    ``NetBoxEndpointResponse`` declares ``verify_ssl`` and ``token_version``
    required, and a row that cannot report them is not a row this backend
    produced — which after a failed push is the one thing that would make its
    stored credentials safe to keep using.
    """
    row = {
        key: value
        for key, value in BACKEND_ROW_THIS_NETBOX.items()
        if key != "token_version"
    }
    _arrange_preflight(monkeypatch, push_ok=False, backend_list=([row], None))
    job, _records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error
    assert "do not point at this NetBox" in result.blocking_error


def test_preflight_blocks_when_the_stored_row_predates_an_in_place_token_rotation(
    monkeypatch, proxbox_sync_job_module
):
    """Same host, same port, same scheme — and a secret the backend no longer has.

    This is the residual the currency check structurally cannot see.
    ``NetBoxEndpointResponse`` withholds ``token`` and ``token_key``, so a v1
    token rotated *in place* leaves every comparable field on the stored row
    identical while the credential proxbox-api would keep writing with is one
    this NetBox has already replaced. Identity says "ours", currency says
    "current", and both are right — the run would still proceed on a revoked
    token.

    The locally recorded fingerprint of the last **successful** push is the only
    evidence that exists locally, and here it says the push carrying the new
    token never landed.
    """
    _arrange_preflight(
        monkeypatch,
        push_ok=False,
        backend_list=([BACKEND_ROW_THIS_NETBOX], None),
        netbox_fingerprint="stale",
    )
    job, records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error, "a superseded secret is not 'still ours'"
    assert (
        "written with different credentials than this NetBox endpoint now carries"
        in result.blocking_error
    )
    # Not the identity arm's wording. The row *does* point at this NetBox, and
    # saying otherwise sends the operator to check the one thing that is fine.
    assert "do not point at this NetBox" not in result.blocking_error
    assert any("different credentials" in entry for entry in records["error"])


def test_preflight_blocks_when_no_push_ever_recorded_a_credential_fingerprint(
    monkeypatch, proxbox_sync_job_module
):
    """An empty fingerprint reads as drifted, because unknown must fail closed.

    Two situations produce it: an endpoint that has never pushed successfully,
    and the first run on an install upgraded into this check. Neither is
    evidence that the credentials proxbox-api holds are the ones this NetBox
    carries — and this branch is only reached *after* a failed push, so the
    alternative is continuing on a credential nothing has vouched for.

    The cost of the fail-closed reading is bounded: one successful push records
    a fingerprint and clears it permanently.
    """
    _arrange_preflight(
        monkeypatch,
        push_ok=False,
        backend_list=([BACKEND_ROW_THIS_NETBOX], None),
        netbox_fingerprint="absent",
    )
    job, records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error, "never-vouched credentials are not 'still ours'"
    assert (
        "written with different credentials than this NetBox endpoint now carries"
        in result.blocking_error
    )
    assert "has never been pushed successfully" in result.blocking_error
    assert any("different credentials" in entry for entry in records["error"])


def _recording_netbox_endpoint(*, update_error=None):
    """A ``NetBoxEndpoint``-shaped row that records how its own row gets written.

    ``_record_pushed_credential_fingerprint()`` must write through
    ``type(endpoint).objects.filter(pk=…).update(…)``. ``save()`` would fire the
    ``post_save`` receiver in ``signals.py`` that pushes the row to proxbox-api —
    from inside the push that is being recorded. So both paths are recorded and
    the tests assert on the pair, not only on the one they want to see.
    """
    calls = {"filter": [], "update": [], "save": []}

    class _Manager:
        def filter(self, **kwargs):
            calls["filter"].append(kwargs)
            return self

        def update(self, **kwargs):
            calls["update"].append(kwargs)
            if update_error is not None:
                raise update_error
            return 1

    class _NetBoxEndpointRow(SimpleNamespace):
        objects = _Manager()

        def save(self, *args, **kwargs):
            calls["save"].append((args, kwargs))

    endpoint = _NetBoxEndpointRow(
        pk=4,
        name="netbox-4",
        domain=THIS_NETBOX_DOMAIN,
        ip_address=None,
        port=443,
        verify_ssl=True,
        effective_token_version="v1",
        effective_token_value="nbt-the-token-this-netbox-carries-now",
        pushed_credential_fingerprint="",
    )
    return endpoint, calls


def test_recording_a_pushed_fingerprint_updates_the_row_without_saving_it():
    """The bookkeeping write must not re-enter the push it is bookkeeping for."""
    backend_sync = load_real_backend_sync()
    endpoint, calls = _recording_netbox_endpoint()
    payload = backend_sync._netbox_endpoint_backend_payload(endpoint)

    backend_sync._record_pushed_credential_fingerprint(endpoint, payload)

    assert calls["save"] == [], (
        "post_save would push to the backend from inside the push"
    )
    assert calls["filter"] == [{"pk": 4}]
    assert calls["update"] == [
        {
            "pushed_credential_fingerprint": backend_sync.netbox_credential_fingerprint(
                payload
            )
        }
    ]
    # Mirrored onto the instance too, so the endpoint reads as vouched for the
    # rest of this request without a refetch.
    assert backend_sync.netbox_push_credentials_unchanged(endpoint) is True


def test_recording_a_pushed_fingerprint_survives_an_unapplied_migration():
    """A missing column must not turn a push that succeeded into one that failed.

    ``ProgrammingError`` subclasses ``DatabaseError``, and it is exactly what the
    first run after an upgrade raises while migration 0073 is unapplied. The push
    has already landed by then, so raising here would report the opposite of what
    happened.

    The instance attribute is left untouched on failure, so the endpoint keeps
    reading as un-vouched — the fail-closed direction, which blocks a later run
    rather than continuing on credentials nothing recorded.
    """
    backend_sync = load_real_backend_sync()
    endpoint, calls = _recording_netbox_endpoint(
        update_error=DatabaseError(
            'column "pushed_credential_fingerprint" does not exist'
        )
    )
    payload = backend_sync._netbox_endpoint_backend_payload(endpoint)

    backend_sync._record_pushed_credential_fingerprint(endpoint, payload)

    assert calls["update"], "the write is attempted, not skipped"
    assert endpoint.pushed_credential_fingerprint == ""
    assert backend_sync.netbox_push_credentials_unchanged(endpoint) is False


def _recording_proxmox_endpoint(*, update_error=None):
    """A ``ProxmoxEndpoint``-shaped row that records how its own row gets written.

    The Proxmox twin of ``_recording_netbox_endpoint()``:
    ``_record_pushed_proxmox_credential_fingerprint()`` must also write through
    ``type(endpoint).objects.filter(pk=…).update(…)``, because ``ProxmoxEndpoint``
    has its own ``post_save`` receiver that pushes the row to proxbox-api.
    """
    calls = {"filter": [], "update": [], "save": []}

    class _Manager:
        def filter(self, **kwargs):
            calls["filter"].append(kwargs)
            return self

        def update(self, **kwargs):
            calls["update"].append(kwargs)
            if update_error is not None:
                raise update_error
            return 1

    class _ProxmoxEndpointRow(SimpleNamespace):
        objects = _Manager()

        def save(self, *args, **kwargs):
            calls["save"].append((args, kwargs))

    endpoint = _ProxmoxEndpointRow(
        pk=7,
        name="pve-7",
        domain="pve-7.example.test",
        ip_address=None,
        port=8006,
        username="root@pam",
        password="the-secret-this-endpoint-carries-now",
        token_name=None,
        token_value=None,
        access_methods="api",
        verify_ssl=False,
        pushed_credential_fingerprint="",
    )
    return endpoint, calls


def test_recording_a_pushed_proxmox_fingerprint_updates_the_row_without_saving_it():
    """The Proxmox bookkeeping write must not re-enter the push either."""
    backend_sync = load_real_backend_sync()
    endpoint, calls = _recording_proxmox_endpoint()
    payload = backend_sync._proxmox_backend_payload(endpoint)

    backend_sync._record_pushed_proxmox_credential_fingerprint(endpoint, payload)

    assert calls["save"] == [], (
        "post_save would push to the backend from inside the push"
    )
    assert calls["filter"] == [{"pk": 7}]
    assert calls["update"] == [
        {
            "pushed_credential_fingerprint": (
                backend_sync.proxmox_credential_fingerprint(payload)
            )
        }
    ]
    # Mirrored onto the instance too, so the soft push budget reads the endpoint
    # as current for the rest of this request without a refetch.
    assert backend_sync.proxmox_push_credentials_unchanged(endpoint, payload) is True


def test_recording_a_pushed_proxmox_fingerprint_survives_an_unapplied_migration():
    """A missing 0074 column must not turn a successful push into a failure.

    Unlike the NetBox twin, the consequence of the fingerprint staying empty is
    *not* a blocked run: ``proxmox_push_credentials_unchanged()`` gates only
    whether the soft push budget may skip a push, so empty reads as "push
    again" — one extra request that records the fingerprint and self-clears.
    """
    backend_sync = load_real_backend_sync()
    endpoint, calls = _recording_proxmox_endpoint(
        update_error=DatabaseError(
            'column "pushed_credential_fingerprint" does not exist'
        )
    )
    payload = backend_sync._proxmox_backend_payload(endpoint)

    backend_sync._record_pushed_proxmox_credential_fingerprint(endpoint, payload)

    assert calls["update"], "the write is attempted, not skipped"
    assert endpoint.pushed_credential_fingerprint == ""
    assert backend_sync.proxmox_push_credentials_unchanged(endpoint, payload) is False


def test_proxmox_and_netbox_credential_fingerprints_never_compare_equal():
    """The two fingerprint namespaces must stay disjoint.

    Both are HMACs over three credential fields, so identical material would
    produce identical digests if the salts ever collapsed into one — and a
    Proxmox fingerprint accidentally landing in the NetBox column (or vice
    versa) would then read as *current*. Distinct salts make the mistake
    self-detecting instead.
    """
    backend_sync = load_real_backend_sync()
    material = {
        "token_version": "s",
        "token_key": "a",
        "token": "b",
        "password": "s",
        "token_name": "a",
        "token_value": "b",
    }
    assert backend_sync.netbox_credential_fingerprint(
        material
    ) != backend_sync.proxmox_credential_fingerprint(material)


def _netbox_row(domain="", ip=None, port=443, verify_ssl=True, token_version="v1"):
    """A local ``NetBoxEndpoint``-shaped row for the identity predicate."""
    return SimpleNamespace(
        pk=1,
        name="netbox-1",
        domain=domain,
        ip_address=SimpleNamespace(address=ip) if ip is not None else None,
        port=port,
        verify_ssl=verify_ssl,
        effective_token_version=token_version,
    )


def _stored_row(**fields):
    """A proxbox-api ``NetBoxEndpointResponse``-shaped row, **current** by default.

    The identity table below varies the connection target; it should not have to
    restate the trust configuration on every row. So the two currency fields the
    backend declares mandatory (`verify_ssl`, `token_version`) default to the
    values `_netbox_row()` pushes, and only the currency table overrides them.
    Both defaults are explicit rather than omitted: an *absent* field reads as
    drifted, which is itself a case the currency table pins.
    """
    return {"verify_ssl": True, "token_version": "v1", **fields}


@pytest.mark.parametrize(
    "endpoint, stored, expected, why",
    [
        # --- positive identification -------------------------------------
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN),
            [_stored_row(domain=THIS_NETBOX_DOMAIN, ip_address="127.0.0.1", port=443)],
            True,
            "our own domain-only record, stored with the push fallback IP",
        ),
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN, ip="10.0.30.207/24"),
            [
                _stored_row(
                    domain=THIS_NETBOX_DOMAIN, ip_address="10.0.30.207", port=443
                )
            ],
            True,
            "both fields agree",
        ),
        (
            _netbox_row(domain="NetBox.Example.Test."),
            [_stored_row(domain="netbox.example.test", ip_address="", port=443)],
            True,
            "case and the trailing root dot are not identity",
        ),
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN, ip="10.0.30.207/24"),
            [_stored_row(domain=THIS_NETBOX_DOMAIN, ip_address="192.0.2.9", port=443)],
            True,
            "with a domain set the backend never dials the address, so a stale "
            "stored IP is not a conflict — it is a field nobody reads",
        ),
        (
            _netbox_row(ip="10.0.30.207/24"),
            [_stored_row(domain="", ip_address="10.0.30.207", port=443)],
            True,
            "an IP-only NetBox is identified by the address the backend dials",
        ),
        (
            _netbox_row(ip="10.0.30.207/24"),
            [_stored_row(domain="", ip_address="10.0.30.207/24", port=443)],
            True,
            "a stored address may carry its mask; the backend strips it first",
        ),
        # --- the loopback trap -------------------------------------------
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN),
            [
                _stored_row(
                    domain="someone-else.example.test",
                    ip_address="127.0.0.1",
                    port=443,
                )
            ],
            False,
            "two domain-only NetBoxes both push 127.0.0.1 — it identifies nobody",
        ),
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN),
            [_stored_row(domain="", ip_address="127.0.0.1", port=443)],
            False,
            "loopback alone is the fallback every domain-only install sends",
        ),
        # --- a different connection target --------------------------------
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN, ip="10.0.30.207/24"),
            [
                _stored_row(
                    domain="someone-else.example.test",
                    ip_address="10.0.30.207",
                    port=443,
                )
            ],
            False,
            "one shared IP, two vhost domains: the backend would dial theirs",
        ),
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN, ip="10.0.30.207/24"),
            [_stored_row(domain="", ip_address="10.0.30.207", port=443)],
            False,
            "a NetBox reached by address is not this one reached by name at "
            "that address — a blank stored domain is data, not a gap",
        ),
        (
            _netbox_row(ip="10.0.30.207/24"),
            [
                _stored_row(
                    domain="someone-else.example.test",
                    ip_address="10.0.30.207",
                    port=443,
                )
            ],
            False,
            "their vhost at our address: our IP matching proves nothing, "
            "because their domain is what gets dialled",
        ),
        # --- the port ------------------------------------------------------
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN),
            [_stored_row(domain=THIS_NETBOX_DOMAIN, port=8443)],
            False,
            "same host, different port is a different service",
        ),
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN, port=8443),
            [_stored_row(domain=THIS_NETBOX_DOMAIN, ip_address="127.0.0.1")],
            False,
            "a row reporting no port identifies no service — proxbox-api "
            "always sends one, so a row without it is not from this backend",
        ),
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN),
            [_stored_row(domain=THIS_NETBOX_DOMAIN, port="not-a-port")],
            False,
            "an unparseable stored port is unknown, and unknown is not ours",
        ),
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN, port="not-a-port"),
            [_stored_row(domain=THIS_NETBOX_DOMAIN, port=443)],
            False,
            "an unparseable local port fails closed too",
        ),
        # --- fail-closed inputs -------------------------------------------
        (_netbox_row(domain=THIS_NETBOX_DOMAIN), [], False, "confirmed empty"),
        (_netbox_row(domain=THIS_NETBOX_DOMAIN), None, False, "listing failed"),
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN),
            ["not-a-dict"],
            False,
            "a junk entry is skipped rather than raising — and skipping the "
            "only row leaves nothing proven, so the answer is still no",
        ),
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN),
            [
                _stored_row(domain=THIS_NETBOX_DOMAIN, port=443),
                _stored_row(domain=THIS_NETBOX_DOMAIN, port=443),
            ],
            False,
            "the singleton is positional: two rows — even two of *ours* — mean "
            "the contract no longer describes the backend, and the response "
            "does not say which one it dials",
        ),
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN),
            ["not-a-dict", _stored_row(domain=THIS_NETBOX_DOMAIN, port=443)],
            False,
            "our row sitting behind another entry is our row in a position the "
            "backend never reads",
        ),
        (
            _netbox_row(),
            [_stored_row(domain=THIS_NETBOX_DOMAIN, ip_address="127.0.0.1", port=443)],
            False,
            "a local row with no host at all can identify nothing",
        ),
    ],
)
def test_backend_holds_netbox_endpoint_identity_contract(
    endpoint, stored, expected, why
):
    """Pin the identity predicate directly, against the real implementation.

    The preflight tests reach this through ``_ensure_backend_endpoints()``, which
    exercises one verdict per test. This table states the contract itself: the
    **resolved connection target** — ``(domain or ip_address)`` plus the port,
    exactly what proxbox-api's own ``NetBoxEndpoint.url`` dials — must be
    present on both sides and equal.

    Comparing fields individually instead is wrong in both directions, and the
    table pins both. It **accepts** rows it should not: a stored row blank on a
    field we declare is a different connection target, not a missing data point
    (rows 10 and 11). And it **rejects** rows it should not: once a domain is
    set the address is never dialled, so a stored record whose IP has since
    changed is still ours (row 4).

    Every stored row here is built by ``_stored_row()``, so it is **current**
    unless the test says otherwise: identity and currency are separate questions
    and the currency table below isolates the second one.
    """
    holds = load_real_backend_sync().backend_holds_netbox_endpoint
    assert holds(endpoint, stored) is expected, why


@pytest.mark.parametrize(
    "endpoint, stored, expected, why",
    [
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN),
            [_stored_row(domain=THIS_NETBOX_DOMAIN, port=443)],
            True,
            "same target, same trust configuration — a transient push failure",
        ),
        # --- drifted trust configuration ----------------------------------
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN, verify_ssl=True),
            [_stored_row(domain=THIS_NETBOX_DOMAIN, port=443, verify_ssl=False)],
            False,
            "the operator turned certificate verification back on and that push "
            "is the one that failed; continuing would write over an unverified "
            "connection the operator had already replaced",
        ),
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN, verify_ssl=False),
            [_stored_row(domain=THIS_NETBOX_DOMAIN, port=443, verify_ssl=True)],
            False,
            "drift is refused in both directions — the stored posture is simply "
            "not the one this NetBox now declares",
        ),
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN, token_version="v2"),
            [_stored_row(domain=THIS_NETBOX_DOMAIN, port=443, token_version="v1")],
            False,
            "the token scheme was rotated; the backend still holds credentials "
            "issued under the superseded one",
        ),
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN, token_version="v1"),
            [_stored_row(domain=THIS_NETBOX_DOMAIN, port=443, token_version="v2")],
            False,
            "and the reverse rotation is drift too",
        ),
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN, token_version="v1"),
            [_stored_row(domain=THIS_NETBOX_DOMAIN, port=443, token_version=" v1 ")],
            True,
            "surrounding whitespace is not a rotation",
        ),
        # --- fields the backend declares mandatory ------------------------
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN),
            [{"domain": THIS_NETBOX_DOMAIN, "port": 443, "token_version": "v1"}],
            False,
            "`verify_ssl` is required on `NetBoxEndpointResponse`, so a row "
            "without one is not a row we can vouch for after a failed push",
        ),
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN),
            [{"domain": THIS_NETBOX_DOMAIN, "port": 443, "verify_ssl": True}],
            False,
            "`token_version` is required for the same reason — absent reads as "
            "drifted, because a False here blocks the run rather than costing "
            "one extra push",
        ),
        # --- currency is only ever asked of the row the backend dials -----
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN),
            [
                _stored_row(domain=THIS_NETBOX_DOMAIN, port=443, verify_ssl=False),
                _stored_row(domain=THIS_NETBOX_DOMAIN, port=443),
            ],
            False,
            "a current duplicate behind a drifted row does not rescue it: the "
            "push overwrites entry [0], so the drifted row is the one the "
            "backend authenticates with and the later match is not consulted",
        ),
        (
            _netbox_row(domain=THIS_NETBOX_DOMAIN),
            [
                _stored_row(domain="someone-else.example.test", port=443),
                _stored_row(domain=THIS_NETBOX_DOMAIN, port=443, token_version="v2"),
            ],
            False,
            "and neither does a current row for a *different* NetBox — twice "
            "over now, since a listing longer than the positional singleton is "
            "refused before currency is asked at all",
        ),
    ],
)
def test_backend_holds_netbox_endpoint_currency_contract(
    endpoint, stored, expected, why
):
    """Identity proves the row is *ours*; it does not prove it is **current**.

    The two answers diverge after a failed push, which is the only situation
    this predicate is consulted in. The push carries `verify_ssl` and
    `token_version` — how proxbox-api must authenticate to us, and whether it
    must verify our certificate — so an operator who tightens either one and
    whose push then fails would have the run continue under the posture they had
    just replaced. That is the same defect class as honouring credentials for a
    NetBox endpoint the operator disabled.

    Only fields the backend both stores **and returns** are comparable.
    `NetBoxEndpointResponse` withholds `token` and `token_key` on purpose, so a
    rotated *secret* under an unchanged scheme is invisible **here** — it is
    caught one step later by `netbox_push_credentials_unchanged()`, which
    compares against the fingerprint the last successful push recorded locally
    rather than against anything the backend returns. `name` is deliberately not
    compared: it has no behavioural effect, and a cosmetic rename must not
    hard-fail an otherwise safe run.
    """
    holds = load_real_backend_sync().backend_holds_netbox_endpoint
    assert holds(endpoint, stored) is expected, why


def test_preflight_blocks_when_the_push_failed_and_the_backend_is_unreadable(
    monkeypatch, proxbox_sync_job_module
):
    """Nothing pushed and nothing readable back is no evidence at all — fail closed.

    A failed *listing* is not evidence of absence, and this branch is not about
    absence: it is about **identity**. Reaching it means our own push failed, so
    the only thing that could make proxbox-api's stored credentials safe to use
    is proving they point at *this* NetBox — and a listing we could not read
    proves nothing. Continuing on "unknown" reintroduces exactly the
    cross-instance write the mismatched-row branch blocks, just through an
    ambiguous read instead of a visibly wrong row.
    """
    _arrange_preflight(
        monkeypatch, push_ok=False, backend_list=(None, "Connection refused")
    )
    job, records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error, "unknown must never read as ours"
    assert "could not read back" in result.blocking_error
    assert "Connection refused" in result.blocking_error, (
        "the operator needs the reason the listing failed, not just that it did"
    )
    assert "http://backend:8800" in result.blocking_error
    assert result.phases == [], "the Proxmox push loop must not run after blocking"


def test_preflight_continues_on_unreadable_backend_when_another_push_succeeded(
    monkeypatch, proxbox_sync_job_module
):
    """One successful push is direct proof; the listing has nothing left to add.

    With several enabled rows, a single failure among them does not put the
    backend's credentials in doubt — a push that *succeeded* wrote this NetBox's
    own credentials into the singleton. The unreadable listing is then merely
    unhelpful, not disqualifying, so this must not be collapsed into the
    fail-closed branch above.
    """
    calls = {"n": 0}

    def _push(*_args, **_kwargs):
        calls["n"] += 1
        # First row pushes cleanly; the second fails.
        if calls["n"] == 1:
            return (True, None, None)
        return (False, "Read timed out. (read timeout=10)", None)

    _arrange_preflight(
        monkeypatch, netbox_rows=(1, 2), backend_list=(None, "Connection refused")
    )
    monkeypatch.setattr(
        sys.modules["netbox_proxbox.views.backend_sync"],
        "sync_netbox_endpoint_to_backend",
        _push,
    )
    job, records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error is None
    assert result.hint and "was not pushed" in result.hint
    assert any(
        "could not verify" in entry and "pushed successfully" in entry
        for entry in records["warning"]
    )


def test_preflight_blocks_when_netbox_has_no_enabled_endpoint(
    monkeypatch, proxbox_sync_job_module
):
    """No enabled NetBoxEndpoint is a hard stop, not a failed push."""
    _arrange_preflight(monkeypatch, netbox_rows=(), backend_list=([], None))
    job, records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error
    assert "has no enabled NetBox endpoint" in result.blocking_error
    assert any("no enabled NetBox endpoint" in entry for entry in records["error"])
    assert result.phases == [], "the Proxmox push loop must not run after blocking"


def test_preflight_blocks_disabled_netbox_endpoint_despite_stale_backend_rows(
    monkeypatch, proxbox_sync_job_module
):
    """A disabled NetBoxEndpoint blocks *even though* proxbox-api still holds rows.

    This is the disabled-endpoint no-connection gate. The stored rows are exactly
    what makes the case dangerous: proxbox-api may still hold credentials issued
    before the row was disabled, or credentials for an entirely different NetBox.
    Honouring them would let the sync keep writing with the authorization the
    operator just revoked, so the backend is deliberately not consulted.
    """
    listed = []

    def _record_listing(*args, **kwargs):
        listed.append((args, kwargs))
        return ([{"id": 7}, {"id": 8}], None)

    _arrange_preflight(monkeypatch, netbox_rows=(), backend_list=([{"id": 7}], None))
    monkeypatch.setattr(
        sys.modules["netbox_proxbox.views.backend_sync"],
        "list_backend_netbox_endpoints",
        _record_listing,
    )
    job, records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error, (
        "stale backend rows must not turn the hard gate into a warning"
    )
    assert "has no enabled NetBox endpoint" in result.blocking_error
    assert "stale or belong to another NetBox instance" in result.blocking_error
    assert listed == [], "the backend must not even be asked once the gate is closed"
    assert records["warning"] == []
    assert result.phases == []


def test_preflight_is_silent_on_the_happy_path(monkeypatch, proxbox_sync_job_module):
    """A clean preflight must add neither a blocking error nor a hint.

    The hint is appended to later stage errors, so a spurious one would
    misattribute an unrelated failure.
    """
    _arrange_preflight(monkeypatch)
    job, records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error is None
    assert result.hint is None
    assert records["error"] == []


def test_preflight_blocks_without_a_backend(monkeypatch, proxbox_sync_job_module):
    """No FastAPI endpoint configured: every stage runs through it, so stop now.

    This used to be a hint only. Letting the run continue meant burning the
    stage retries and then reporting whichever backend-proxy error surfaced
    first, which is the same misattribution the preflight exists to prevent.
    """
    monkeypatch.setattr(
        sys.modules["netbox_proxbox.services.backend_context"],
        "get_fastapi_request_context",
        lambda **kwargs: None,
    )
    job, records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(job)

    assert result.blocking_error
    assert "no usable proxbox-api backend" in result.blocking_error
    assert "Proxbox → Endpoints → FastAPI" in result.blocking_error, (
        "the operator needs to be told where to fix it"
    )
    assert any("no usable proxbox-api backend" in entry for entry in records["error"])
    assert result.hint and "no enabled FastAPI endpoint" in result.hint


def test_preflight_names_the_selected_backend_when_it_is_unusable(
    monkeypatch, proxbox_sync_job_module
):
    """A job pinned to one backend must say *which* one it could not use."""
    monkeypatch.setattr(
        sys.modules["netbox_proxbox.services.backend_context"],
        "get_fastapi_request_context",
        lambda **kwargs: None,
    )
    job, _records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(
        job, [], fastapi_endpoint_id=4
    )

    assert result.blocking_error and "selected endpoint id 4" in result.blocking_error


def test_preflight_checks_the_backend_the_stages_will_use(
    monkeypatch, proxbox_sync_job_module
):
    """With two enabled backends, the preflight must not check the wrong one.

    Backend 1 is cold and holds nothing; backend 2 is the selected, healthy one.
    Resolving the context without the id would return backend 1 and hard-fail a
    sync that works — and, in reverse, pass a sync that cannot.
    """
    seen: list[object] = []

    def _context(endpoint_id=None, **kwargs):
        seen.append(endpoint_id)
        if endpoint_id == 2:
            return _preflight_context()
        return None

    _arrange_preflight(monkeypatch)
    monkeypatch.setattr(
        sys.modules["netbox_proxbox.services.backend_context"],
        "get_fastapi_request_context",
        _context,
    )
    job, _records = _preflight_job()

    result = proxbox_sync_job_module._ensure_backend_endpoints(
        job, [], fastapi_endpoint_id=2
    )

    assert seen == [2], "the selected backend id must reach the context resolver"
    assert result.blocking_error is None


def test_preflight_scopes_key_registration_to_the_selected_backend(
    monkeypatch, proxbox_sync_job_module
):
    """Key registration targets one backend too — it must be the same one."""
    seen: dict[str, object] = {}

    def _register(endpoint_id=None, **kwargs):
        seen["endpoint_id"] = endpoint_id
        return (True, "registered")

    _arrange_preflight(monkeypatch)
    monkeypatch.setattr(
        sys.modules["netbox_proxbox.services.backend_auth"],
        "ensure_backend_key_registered",
        _register,
    )
    job, _records = _preflight_job()

    proxbox_sync_job_module._ensure_backend_endpoints(job, [], fastapi_endpoint_id=9)

    assert seen["endpoint_id"] == 9


def _preflight_proxmox_endpoint(pk):
    """Return an enabled Proxmox endpoint stub that resolves a connection target.

    The budget tests only care about *which* endpoints get pushed, but the
    preflight decides "already held" with `backend_holds_proxmox_endpoint()`,
    which refuses a row it cannot confirm still dials the same `(host, port)` —
    so an endpoint carrying no host fields at all is never held, and every
    budget test would degrade into the never-held case.
    """
    return SimpleNamespace(
        pk=pk,
        enabled=True,
        name=f"pve-{pk}",
        domain=f"pve-{pk}.example.test",
        ip_address=None,
        port=8006,
        username="root@pam",
        access_methods="api",
        verify_ssl=False,
    )


def _arrange_slow_push(monkeypatch, module, *, seconds=6.0, held=()):
    """Give the preflight a fake clock advanced by each push, and a held-rows list.

    ``held`` are the endpoint stubs proxbox-api already holds, and the rows built
    for them are *current* — same target, same pushed configuration — because a
    drifted row still needs its push and would not be skipped. "Current" now
    also covers the credentials, which the backend row cannot report: each held
    endpoint gets the fingerprint a previous successful push of its present
    credentials would have recorded, computed through the **real**
    ``proxmox_endpoint_credential_fingerprint()`` — a literal here would stop
    tracking the code the moment the material or the salt changed.
    """
    backend_sync = sys.modules["netbox_proxbox.views.backend_sync"]
    _real_backend_sync = load_real_backend_sync()
    for endpoint in held:
        endpoint.pushed_credential_fingerprint = (
            _real_backend_sync.proxmox_endpoint_credential_fingerprint(endpoint)
        )
    clock = {"now": 0.0}
    pushed: list[str] = []

    def _slow_push(endpoint, **kwargs):
        pushed.append(endpoint.name)
        clock["now"] += seconds
        return (True, None, None)

    held_rows = [
        {
            "id": endpoint.pk,
            "name": f"{endpoint.name} (nb:{endpoint.pk})",
            "domain": endpoint.domain,
            "ip_address": endpoint.ip_address or "",
            "port": endpoint.port,
            "username": endpoint.username,
            "access_methods": endpoint.access_methods,
            "verify_ssl": endpoint.verify_ssl,
        }
        for endpoint in held
    ]

    monkeypatch.setattr(backend_sync, "sync_proxmox_endpoint_to_backend", _slow_push)
    monkeypatch.setattr(
        backend_sync,
        "list_backend_proxmox_endpoints",
        lambda *a, **kw: (held_rows, None),
    )
    monkeypatch.setattr(
        module,
        "time",
        SimpleNamespace(monotonic=lambda: clock["now"], sleep=lambda _: None),
    )
    return pushed


def test_preflight_stops_pushing_once_the_endpoint_budget_is_exhausted(
    monkeypatch, proxbox_sync_job_module
):
    """A slow backend must not let the preflight eat the whole job timeout.

    Each push carries its own request timeout, so an estate with many Proxmox
    endpoints and an unresponsive backend serializes into (endpoints × timeout)
    seconds *before the first stage runs*. Past the budget a **refresh** push is
    dropped and the stages run instead: the backend already holds those rows, and
    a stage failure is far more diagnosable than a job that died before reaching
    one.
    """
    module = proxbox_sync_job_module
    backend_sync = sys.modules["netbox_proxbox.views.backend_sync"]
    rows = [_preflight_proxmox_endpoint(pk) for pk in (1, 2, 3, 4)]

    _arrange_preflight(monkeypatch)
    monkeypatch.setattr(
        sys.modules["netbox_proxbox.models"].ProxmoxEndpoint.objects, "rows", rows
    )
    monkeypatch.setattr(backend_sync, "PREFLIGHT_ENDPOINT_PUSH_BUDGET", 10.0)

    # Two 6s pushes exceed a 10s budget, so endpoints 3 and 4 — both of which the
    # backend already holds a *current* row for — must never be attempted.
    pushed = _arrange_slow_push(monkeypatch, module, held=rows)
    job, records = _preflight_job()

    result = module._ensure_backend_endpoints(job)

    assert pushed == ["pve-1", "pve-2"], "the budget must cut the loop short"
    assert result.blocking_error is None, "an exhausted budget is not fatal"

    statuses = [phase["status"] for phase in result.phases]
    assert statuses == ["success", "success", "warning", "warning"], (
        "skipped endpoints still get a phase, so the run is visibly incomplete"
    )
    skipped = [p for p in result.phases if p["status"] == "warning"]
    assert all("budget of 10s was exhausted" in p["summary"] for p in skipped)

    assert any(
        "pve-3, pve-4" in entry and "budget was exhausted" in entry
        for entry in records["warning"]
    ), "the operator needs to know *which* endpoints were not pushed"
    assert result.hint and "2 Proxmox endpoint(s) were not pushed" in result.hint


def test_preflight_budget_never_skips_an_endpoint_the_backend_does_not_hold(
    monkeypatch, proxbox_sync_job_module
):
    """Skipping an unregistered endpoint is worse than being slow.

    The push is the *only* thing that gives proxbox-api the endpoint, so a
    budget-skipped fresh endpoint has no backend id at all and the run later dies
    resolving it — failing on exactly the endpoint the budget "saved" time on. A
    fresh estate hits this trivially: 21 endpoints × a 30 s push already exceeds
    the 600 s budget.
    """
    module = proxbox_sync_job_module
    backend_sync = sys.modules["netbox_proxbox.views.backend_sync"]
    rows = [_preflight_proxmox_endpoint(pk) for pk in (1, 2, 3, 4)]

    _arrange_preflight(monkeypatch)
    monkeypatch.setattr(
        sys.modules["netbox_proxbox.models"].ProxmoxEndpoint.objects, "rows", rows
    )
    monkeypatch.setattr(backend_sync, "PREFLIGHT_ENDPOINT_PUSH_BUDGET", 10.0)

    # Same exhausted budget as the test above — but the backend holds nothing.
    pushed = _arrange_slow_push(monkeypatch, module, held=())
    job, _records = _preflight_job()

    result = module._ensure_backend_endpoints(job)

    assert pushed == ["pve-1", "pve-2", "pve-3", "pve-4"]
    assert result.blocking_error is None
    assert all(phase["status"] == "success" for phase in result.phases)
    assert not result.hint, "nothing was skipped, so there is nothing to warn about"


def test_preflight_hard_ceiling_skips_even_unregistered_endpoints(
    monkeypatch, proxbox_sync_job_module
):
    """Past the ceiling the backend is not slow, it is hung — waiting cannot help.

    The soft budget keeps pushing unregistered endpoints indefinitely, which is
    right for a merely slow backend and wrong for a dead one. The ceiling is what
    keeps the preflight from consuming the whole ``PROXBOX_SYNC_JOB_TIMEOUT``.
    """
    module = proxbox_sync_job_module
    backend_sync = sys.modules["netbox_proxbox.views.backend_sync"]
    rows = [_preflight_proxmox_endpoint(pk) for pk in (1, 2, 3, 4)]

    _arrange_preflight(monkeypatch)
    monkeypatch.setattr(
        sys.modules["netbox_proxbox.models"].ProxmoxEndpoint.objects, "rows", rows
    )
    monkeypatch.setattr(backend_sync, "PREFLIGHT_ENDPOINT_PUSH_BUDGET", 10.0)
    monkeypatch.setattr(backend_sync, "PREFLIGHT_ENDPOINT_PUSH_HARD_CEILING", 12.0)

    pushed = _arrange_slow_push(monkeypatch, module, held=())
    job, _records = _preflight_job()

    result = module._ensure_backend_endpoints(job)

    assert pushed == ["pve-1", "pve-2"], "the ceiling stops even fresh endpoints"
    assert result.blocking_error is None
    skipped = [p for p in result.phases if p["status"] == "warning"]
    assert len(skipped) == 2
    assert all("hard ceiling of 12s was reached" in p["summary"] for p in skipped)


def test_preflight_budget_never_skips_an_endpoint_whose_credentials_rotated(
    monkeypatch, proxbox_sync_job_module
):
    """A rotated secret is invisible to the backend row — only the push fixes it.

    ``ProxmoxEndpointPublic`` withholds ``password``/``token_name``/
    ``token_value``, so a secret rotated *in place* — same host, same username,
    same access methods — produces a backend row that reads byte-identical to a
    current one. Skipping that push under the soft budget would leave proxbox-api
    authenticating with the credential the operator has just revoked. The
    locally recorded fingerprint of the last successful push is the only thing
    that can tell, and both a stale fingerprint *and* a never-recorded one must
    read as "push again" — the fail-closed direction on this side is one extra
    request, not a blocked run.
    """
    module = proxbox_sync_job_module
    backend_sync = sys.modules["netbox_proxbox.views.backend_sync"]
    rows = [_preflight_proxmox_endpoint(pk) for pk in (1, 2, 3, 4)]

    _arrange_preflight(monkeypatch)
    monkeypatch.setattr(
        sys.modules["netbox_proxbox.models"].ProxmoxEndpoint.objects, "rows", rows
    )
    monkeypatch.setattr(backend_sync, "PREFLIGHT_ENDPOINT_PUSH_BUDGET", 10.0)

    # All four rows are held and *current* as far as the backend can report.
    pushed = _arrange_slow_push(monkeypatch, module, held=rows)
    # Endpoint 3's secret rotates *after* the fingerprint of its last push was
    # recorded; endpoint 4 has never had a fingerprint recorded at all (the
    # pre-upgrade state). Both must be pushed despite the exhausted budget.
    rows[2].password = "rotated-in-place"
    rows[3].pushed_credential_fingerprint = ""
    job, _records = _preflight_job()

    result = module._ensure_backend_endpoints(job)

    assert pushed == ["pve-1", "pve-2", "pve-3", "pve-4"], (
        "a rotated or never-vouched credential is never 'already held'"
    )
    assert result.blocking_error is None
    assert all(phase["status"] == "success" for phase in result.phases)


def test_run_passes_the_selected_backend_to_the_preflight(
    monkeypatch, proxbox_sync_job_module
):
    """`run()` must forward its own `fastapi_endpoint_id`, not drop it."""
    module = proxbox_sync_job_module
    seen: dict[str, object] = {}
    services_mod = types.ModuleType("netbox_proxbox.services")
    services_mod.run_sync_stream = lambda path, **kwargs: ({"response": {}}, 200)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    def _preflight(job, ids=None, fastapi_endpoint_id=None):
        seen["ids"] = ids
        seen["fastapi_endpoint_id"] = fastapi_endpoint_id
        return module.PreflightResult(blocking_error="stop here")

    monkeypatch.setattr(module, "_ensure_backend_endpoints", _preflight)

    job = module.ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job_preflight_selected_backend")
    job.job = MagicMock()
    job.job.data = None

    with pytest.raises(module.ProxboxPreflightError):
        module.ProxboxSyncJob.run(
            job,
            sync_types=[module.SyncTypeChoices.DEVICES],
            proxmox_endpoint_ids=["1"],
            fastapi_endpoint_id=3,
        )

    assert seen["fastapi_endpoint_id"] == 3


def test_run_passes_the_selected_backend_to_every_pre_sse_service(
    monkeypatch, proxbox_sync_job_module
):
    """All four pre-SSE passes must talk to the backend the preflight certified.

    Cluster/node, firewall, datacenter and VM-template sync each run **before**
    the SSE stages and each resolve their own backend context. With two enabled
    `FastAPIEndpoint` rows, a pass that re-resolves without the id certifies
    backend A in the preflight and then syncs against backend B — silently
    writing one backend's Proxmox state into NetBox under the other's scope.

    They take `fastapi_endpoint_id` rather than `fastapi_url` on purpose: all
    four set `verify_ssl = True` and only override it from the resolved context
    *when no url was supplied*, so passing a url would force certificate
    verification on and break every self-signed backend.
    """
    module = proxbox_sync_job_module
    seen: dict[str, object] = {}

    services_mod = types.ModuleType("netbox_proxbox.services")
    services_mod.run_sync_stream = lambda path, **kwargs: (
        {"stream": True, "response": {"ok": True}},
        200,
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    def _record(name, result):
        def _call(*args, **kwargs):
            seen[name] = kwargs.get("fastapi_endpoint_id", "<missing>")
            return result

        return _call

    ok = SimpleNamespace(
        success=True,
        error=None,
        endpoint_id=1,
        endpoint_name="pve-1",
        endpoints_processed=1,
        clusters_created=0,
        clusters_updated=0,
        nodes_created=0,
        nodes_updated=0,
        security_groups_created=0,
        security_groups_updated=0,
        rules_created=0,
        ipsets_created=0,
        aliases_created=0,
        cpu_models_created=0,
        cpu_models_updated=0,
        cpu_models_stale=0,
        templates_created=0,
        templates_updated=0,
        templates_skipped=0,
        templates_deleted=0,
        per_endpoint=[],
    )
    for module_name, attr, key in (
        ("sync_cluster", "sync_cluster_and_nodes", "cluster"),
        ("sync_firewall", "sync_firewall", "firewall"),
        ("sync_datacenter", "sync_datacenter", "datacenter"),
        ("sync_vm_template", "sync_vm_templates", "vm_template"),
    ):
        monkeypatch.setattr(
            sys.modules[f"netbox_proxbox.services.{module_name}"],
            attr,
            _record(key, ok),
        )

    monkeypatch.setattr(
        module, "_ensure_backend_endpoints", lambda *a, **kw: module.PreflightResult()
    )
    monkeypatch.setattr(
        module.sync_stages,
        "_resolve_wire_endpoint_ids",
        lambda scopes, **kwargs: (
            {scope[0]: scope[0] + "00" for scope in scopes},
            None,
        ),
    )

    job = module.ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job_backend_threading")
    job.job = MagicMock()
    job.job.data = None

    module.ProxboxSyncJob.run(
        job,
        sync_types=[module.SyncTypeChoices.DEVICES],
        proxmox_endpoint_ids=["1"],
        fastapi_endpoint_id=3,
    )

    assert seen == {
        "cluster": 3,
        "firewall": 3,
        "datacenter": 3,
        "vm_template": 3,
    }


def test_run_scopes_firewall_and_datacenter_to_the_runs_endpoints(
    monkeypatch, proxbox_sync_job_module
):
    """The firewall and datacenter passes must honour the job's endpoint scope.

    Both passes used to build their own all-enabled scope, so a job launched
    against one endpoint still synced every enabled endpoint's firewall objects
    and CPU models — an *absent* endpoint filter is the widest request
    proxbox-api accepts, not a narrower one. `run()` therefore forwards the same
    `endpoint_ids_to_sync` the cluster/node loop and the stage scope are built
    from. Cluster/node sync is already per-endpoint (`endpoint_id=`) and the
    VM-template pass iterates that list itself, so those two need no forwarding.
    """
    module = proxbox_sync_job_module
    seen: dict[str, object] = {}

    services_mod = types.ModuleType("netbox_proxbox.services")
    services_mod.run_sync_stream = lambda path, **kwargs: (
        {"stream": True, "response": {"ok": True}},
        200,
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    def _record(name, result):
        def _call(*args, **kwargs):
            seen[name] = kwargs.get("endpoint_ids", "<missing>")
            return result

        return _call

    ok = SimpleNamespace(
        success=True,
        error=None,
        endpoint_id=1,
        endpoint_name="pve-1",
        endpoints_processed=1,
        security_groups_created=0,
        security_groups_updated=0,
        rules_created=0,
        ipsets_created=0,
        aliases_created=0,
        cpu_models_created=0,
        cpu_models_updated=0,
        cpu_models_stale=0,
        per_endpoint=[],
    )
    for module_name, attr, key in (
        ("sync_firewall", "sync_firewall", "firewall"),
        ("sync_datacenter", "sync_datacenter", "datacenter"),
    ):
        monkeypatch.setattr(
            sys.modules[f"netbox_proxbox.services.{module_name}"],
            attr,
            _record(key, ok),
        )

    monkeypatch.setattr(
        module, "_ensure_backend_endpoints", lambda *a, **kw: module.PreflightResult()
    )
    monkeypatch.setattr(
        module.sync_stages,
        "_resolve_wire_endpoint_ids",
        lambda scopes, **kwargs: (
            {scope[0]: scope[0] + "00" for scope in scopes},
            None,
        ),
    )

    job = module.ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job_pre_sse_endpoint_scope")
    job.job = MagicMock()
    job.job.data = None

    module.ProxboxSyncJob.run(
        job,
        sync_types=[module.SyncTypeChoices.DEVICES],
        proxmox_endpoint_ids=["1"],
    )

    assert seen == {"firewall": [1], "datacenter": [1]}, (
        "both passes must receive the run's own endpoint selection"
    )


def test_run_raises_on_a_blocking_preflight(monkeypatch, proxbox_sync_job_module):
    """The blocking error must actually stop `run()`, not just be returned."""
    module = proxbox_sync_job_module
    services_mod = types.ModuleType("netbox_proxbox.services")
    services_mod.run_sync_stream = lambda path, **kwargs: ({"response": {}}, 200)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)

    monkeypatch.setattr(
        module,
        "_ensure_backend_endpoints",
        lambda job, ids=None, **kwargs: module.PreflightResult(
            blocking_error="backend is empty"
        ),
    )

    job = module.ProxboxSyncJob()
    job.logger = logging.getLogger("test_proxbox_job_preflight_block")
    job.job = MagicMock()
    job.job.data = None

    with pytest.raises(module.ProxboxPreflightError, match="backend is empty"):
        module.ProxboxSyncJob.run(
            job, sync_types=[module.SyncTypeChoices.DEVICES], proxmox_endpoint_ids=["1"]
        )


def test_preflight_result_defaults_are_not_shared(proxbox_sync_job_module):
    """`phases` must be a fresh list per instance, not a shared default."""
    first = proxbox_sync_job_module.PreflightResult()
    second = proxbox_sync_job_module.PreflightResult()
    first.phases.append({"kind": "preflight"})

    assert second.phases == []
