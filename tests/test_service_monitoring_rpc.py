"""Behavior tests for async netbox-rpc service monitoring integration."""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]


class _QuerySet(list):
    def first(self):
        return self[0] if self else None

    def select_related(self, *args):
        return self

    def order_by(self, *args):
        return self


def _load_rpc_module():
    path = REPO_ROOT / "netbox_proxbox" / "integrations" / "rpc.py"
    spec = importlib.util.spec_from_file_location("nbp_rpc_service_test", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _install_netbox_rpc_stubs(monkeypatch, *, procedure, execution, executions=None):
    class _ProcedureManager:
        def filter(self, **kwargs):
            assert kwargs == {
                "name": "os.linux.proxmox.show_systemctl_services",
                "enabled": True,
            }
            return _QuerySet([procedure] if procedure is not None else [])

    class _ExecutionManager:
        created = []

        def create(self, **kwargs):
            self.created.append(kwargs)
            return execution

        def filter(self, **kwargs):
            assert "pk__in" in kwargs
            wanted = set(kwargs["pk__in"])
            return _QuerySet(
                [item for item in list(executions or []) if item.pk in wanted]
            )

    execution_manager = _ExecutionManager()

    class _RPCProcedure:
        objects = _ProcedureManager()

    class _RPCExecution:
        objects = execution_manager

    enqueue_calls = []

    class _RPCExecutionJob:
        @classmethod
        def enqueue(cls, **kwargs):
            enqueue_calls.append(kwargs)

    package = types.ModuleType("netbox_rpc")
    package.__path__ = []
    jobs = types.ModuleType("netbox_rpc.jobs")
    jobs.RPCExecutionJob = _RPCExecutionJob
    models = types.ModuleType("netbox_rpc.models")
    models.RPCExecution = _RPCExecution
    models.RPCProcedure = _RPCProcedure

    monkeypatch.setitem(sys.modules, "netbox_rpc", package)
    monkeypatch.setitem(sys.modules, "netbox_rpc.jobs", jobs)
    monkeypatch.setitem(sys.modules, "netbox_rpc.models", models)
    return execution_manager, enqueue_calls


def _install_model_stubs(
    monkeypatch,
    *,
    collections=None,
    sample_calls=None,
    status_calls=None,
    status_by_unit=None,
):
    sample_calls = sample_calls if sample_calls is not None else []
    status_calls = status_calls if status_calls is not None else []
    status_by_unit = status_by_unit if status_by_unit is not None else {}
    created_collections = []
    next_status_pk = len(status_by_unit) + 1
    for index, status in enumerate(status_by_unit.values(), start=1):
        if getattr(status, "pk", None) is None:
            status.pk = index
        if not hasattr(status, "update_calls"):
            status.update_calls = []

    class _CollectionManager:
        def create(self, **kwargs):
            collection = SimpleNamespace(**kwargs)
            collection.saved = []
            collection.save = lambda **save_kwargs: collection.saved.append(save_kwargs)
            created_collections.append(collection)
            return collection

        def filter(self, **kwargs):
            return _QuerySet(list(collections or []))

    class _SampleManager:
        def update_or_create(self, **kwargs):
            sample_calls.append(kwargs)
            return SimpleNamespace(**kwargs), True

    class _StatusUpdateQuerySet:
        def __init__(self, *, pk=None, conditional=False):
            self.pk = pk
            self.conditional = conditional

        def filter(self, *args, **kwargs):
            pk = kwargs.get("pk", self.pk)
            conditional = (
                self.conditional
                or bool(args)
                or any(key.startswith("last_seen_at__") for key in kwargs)
            )
            return _StatusUpdateQuerySet(pk=pk, conditional=conditional)

        def update(self, **values):
            status = next(
                (
                    status
                    for status in status_by_unit.values()
                    if getattr(status, "pk", None) == self.pk
                ),
                None,
            )
            matched = 0
            if status is not None and self._timestamp_matches(status, values):
                for field, value in values.items():
                    setattr(status, field, value)
                matched = 1
            if status is not None:
                status.update_calls.append(
                    {
                        "matched": matched,
                        "pk": self.pk,
                        "values": values,
                    }
                )
            return matched

        def _timestamp_matches(self, status, values):
            if not self.conditional:
                return True
            current = getattr(status, "last_seen_at", None)
            incoming = values.get("last_seen_at")
            if current is None:
                return True
            if incoming is None:
                return False
            try:
                return current < incoming
            except TypeError:
                return True

    class _StatusManager:
        def get_or_create(self, **kwargs):
            nonlocal next_status_pk
            status_calls.append(kwargs)
            existing = status_by_unit.get(kwargs["unit"])
            if existing is not None:
                return existing, False
            defaults = dict(kwargs.get("defaults") or {})
            status = SimpleNamespace(
                endpoint=kwargs["endpoint"],
                unit=kwargs["unit"],
                pk=next_status_pk,
                **defaults,
            )
            next_status_pk += 1
            if not hasattr(status, "expected_active"):
                status.expected_active = True
            status.saved = []
            status.update_calls = []
            status.save = lambda **save_kwargs: status.saved.append(save_kwargs)
            status_by_unit[kwargs["unit"]] = status
            return status, True

        def filter(self, *args, **kwargs):
            return _StatusUpdateQuerySet().filter(*args, **kwargs)

    class _ProxmoxServiceCollection:
        objects = _CollectionManager()

    class _ProxmoxServiceSample:
        objects = _SampleManager()

    class _ProxmoxServiceStatus:
        objects = _StatusManager()

    class _Q:
        def __init__(self, *args, **kwargs):
            pass

        def __or__(self, other):
            return self

    django = types.ModuleType("django")
    django.__path__ = []
    django_db = types.ModuleType("django.db")
    django_db.__path__ = []
    django_db_models = types.ModuleType("django.db.models")
    django_db_models.Q = _Q
    django.db = django_db
    django_db.models = django_db_models

    package = types.ModuleType("netbox_proxbox")
    package.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    models = types.ModuleType("netbox_proxbox.models")
    models.ProxmoxServiceCollection = _ProxmoxServiceCollection
    models.ProxmoxServiceSample = _ProxmoxServiceSample
    models.ProxmoxServiceStatus = _ProxmoxServiceStatus

    service_monitoring = types.ModuleType("netbox_proxbox.models.service_monitoring")
    service_monitoring.SERVICE_COLLECTION_STATUS_FAILED = "failed"
    service_monitoring.SERVICE_COLLECTION_STATUS_PENDING = "pending"
    service_monitoring.SERVICE_COLLECTION_STATUS_SUCCEEDED = "succeeded"
    service_monitoring.SERVICE_COLLECTION_TRIGGER_ON_DEMAND = "on_demand"
    service_monitoring.SERVICE_COLLECTION_TRIGGER_SCHEDULED = "scheduled"

    monkeypatch.setitem(sys.modules, "django", django)
    monkeypatch.setitem(sys.modules, "django.db", django_db)
    monkeypatch.setitem(sys.modules, "django.db.models", django_db_models)
    monkeypatch.setitem(sys.modules, "netbox_proxbox", package)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models)
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.models.service_monitoring",
        service_monitoring,
    )
    return created_collections, sample_calls, status_calls


def test_collect_systemctl_services_creates_execution_collection_and_enqueue(
    monkeypatch,
):
    mod = _load_rpc_module()
    procedure = SimpleNamespace(pk=7)
    execution = SimpleNamespace(pk=123)
    backend = SimpleNamespace(pk=456)
    endpoint = SimpleNamespace(
        pk=42,
        service_monitoring_enabled=True,
        service_monitoring_eligible=True,
        service_monitoring_units=["pve-cluster.service"],
    )
    user = SimpleNamespace(username="operator")
    execution_manager, enqueue_calls = _install_netbox_rpc_stubs(
        monkeypatch,
        procedure=procedure,
        execution=execution,
    )
    created_collections, _sample_calls, _status_calls = _install_model_stubs(
        monkeypatch
    )

    nms_pkg = types.ModuleType("netbox_nms")
    nms_pkg.__path__ = []
    nms_backend = types.ModuleType("netbox_nms.backend")
    nms_backend.get_backend = lambda: backend
    monkeypatch.setitem(sys.modules, "netbox_nms", nms_pkg)
    monkeypatch.setitem(sys.modules, "netbox_nms.backend", nms_backend)

    result = mod.collect_systemctl_services(
        endpoint,
        requested_by=user,
        trigger="on_demand",
    )

    assert result is execution
    assert execution_manager.created == [
        {
            "procedure": procedure,
            "assigned_object": endpoint,
            "backend": backend,
            "requested_by": user,
            "params": {
                "proxmox_endpoint_id": 42,
                "units": ["pve-cluster.service"],
            },
            "status": "queued",
        }
    ]
    assert len(created_collections) == 1
    collection = created_collections[0]
    assert collection.endpoint is endpoint
    assert collection.trigger == "on_demand"
    assert collection.rpc_execution_id == 123
    assert collection.status == "pending"
    assert enqueue_calls == [
        {
            "execution_pk": 123,
            "instance": None,
            "user": user,
            "backend_pk": 456,
        }
    ]


def test_collect_systemctl_services_skips_disabled_endpoint(monkeypatch):
    # A disabled endpoint is a hard no-connection gate: no RPC is dispatched even
    # when monitoring is enabled and eligible.
    mod = _load_rpc_module()
    execution_manager, enqueue_calls = _install_netbox_rpc_stubs(
        monkeypatch,
        procedure=SimpleNamespace(pk=7),
        execution=SimpleNamespace(pk=1),
    )
    created_collections, _sample_calls, _status_calls = _install_model_stubs(
        monkeypatch
    )
    endpoint = SimpleNamespace(
        pk=42,
        enabled=False,
        service_monitoring_enabled=True,
        service_monitoring_eligible=True,
        service_monitoring_units=[],
    )

    result = mod.collect_systemctl_services(endpoint, trigger="scheduled")

    assert result is None
    assert execution_manager.created == []
    assert enqueue_calls == []
    assert created_collections == []
    assert endpoint.service_monitoring_last_status == "endpoint_disabled"


def _endpoint():
    endpoint = SimpleNamespace(pk=42)
    endpoint.saved = []
    endpoint.save = lambda **kwargs: endpoint.saved.append(kwargs)
    return endpoint


def _collection(endpoint):
    collection = SimpleNamespace(
        pk=9,
        endpoint=endpoint,
        rpc_execution_id=123,
        status="pending",
        reachable=False,
        collected_at=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
    )
    collection.saved = []
    collection.save = lambda **kwargs: collection.saved.append(kwargs)
    return collection


def test_project_completed_collections_projects_samples_status_and_heartbeat(
    monkeypatch,
):
    mod = _load_rpc_module()
    endpoint = _endpoint()
    collection = _collection(endpoint)
    execution = SimpleNamespace(
        pk=123,
        status="succeeded",
        completed_at=datetime(2026, 7, 10, 12, 2, tzinfo=timezone.utc),
        result={
            "ok": True,
            "procedure": "os.linux.proxmox.show_systemctl_services",
            "target": "pve-01",
            "reachable": True,
            "services": [
                {
                    "unit": "pveproxy.service",
                    "id": "pveproxy.service",
                    "load_state": "loaded",
                    "active_state": "active",
                    "sub_state": "running",
                    "result": "success",
                    "main_pid": 100,
                    "exec_main_code": 0,
                    "exec_main_status": 0,
                    "n_restarts": 1,
                    "active_enter_timestamp": "Fri 2026-07-10 11:59:00 UTC",
                    "unit_file_state": "enabled",
                }
            ],
        },
    )
    _install_netbox_rpc_stubs(
        monkeypatch,
        procedure=SimpleNamespace(pk=7),
        execution=execution,
        executions=[execution],
    )
    _created, sample_calls, status_calls = _install_model_stubs(
        monkeypatch,
        collections=[collection],
    )

    assert mod.project_completed_collections() == 1
    assert collection.status == "succeeded"
    assert collection.reachable is True
    assert endpoint.service_monitoring_last_status == "succeeded"
    assert endpoint.service_monitoring_last_error == ""
    assert endpoint.service_monitoring_last_success_at == execution.completed_at
    assert sample_calls[0]["unit"] == "pveproxy.service"
    assert sample_calls[0]["defaults"]["active_state"] == "active"
    assert status_calls[0]["unit"] == "pveproxy.service"
    assert status_calls[0]["defaults"]["is_healthy"] is True


def test_project_service_rows_does_not_regress_newer_latest_status(monkeypatch):
    mod = _load_rpc_module()
    endpoint = _endpoint()
    collection = _collection(endpoint)
    existing_status = SimpleNamespace(
        expected_active=True,
        last_seen_at=datetime(2026, 7, 10, 12, 5, tzinfo=timezone.utc),
        active_state="active",
        is_healthy=True,
        saved=[],
    )
    existing_status.save = lambda **kwargs: existing_status.saved.append(kwargs)
    _created, sample_calls, status_calls = _install_model_stubs(
        monkeypatch,
        status_by_unit={"pveproxy.service": existing_status},
    )

    assert (
        mod._project_service_rows(
            collection,
            [
                {
                    "unit": "pveproxy.service",
                    "id": "pveproxy.service",
                    "load_state": "loaded",
                    "active_state": "failed",
                    "sub_state": "failed",
                    "result": "exit-code",
                }
            ],
            datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
        )
        == 1
    )

    assert sample_calls[0]["unit"] == "pveproxy.service"
    assert status_calls[0]["unit"] == "pveproxy.service"
    assert existing_status.update_calls[0]["matched"] == 0
    assert existing_status.last_seen_at == datetime(
        2026,
        7,
        10,
        12,
        5,
        tzinfo=timezone.utc,
    )
    assert existing_status.active_state == "active"
    assert existing_status.is_healthy is True
    assert existing_status.saved == []


def test_project_completed_collections_does_not_starve_terminal_after_stuck_pending(
    monkeypatch,
):
    mod = _load_rpc_module()
    endpoint = _endpoint()
    stuck_collection = _collection(endpoint)
    stuck_collection.pk = 1
    stuck_collection.rpc_execution_id = 999
    stuck_collection.collected_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    terminal_collection = _collection(endpoint)
    terminal_collection.pk = 2
    terminal_collection.rpc_execution_id = 123
    terminal_collection.collected_at = datetime(
        2026,
        7,
        10,
        12,
        0,
        tzinfo=timezone.utc,
    )
    execution = SimpleNamespace(
        pk=123,
        status="succeeded",
        completed_at=datetime(2026, 7, 10, 12, 1, tzinfo=timezone.utc),
        result={
            "ok": True,
            "reachable": True,
            "services": [
                {
                    "unit": "pvedaemon.service",
                    "id": "pvedaemon.service",
                    "load_state": "loaded",
                    "active_state": "active",
                    "sub_state": "running",
                    "result": "success",
                }
            ],
        },
    )
    _install_netbox_rpc_stubs(
        monkeypatch,
        procedure=SimpleNamespace(pk=7),
        execution=execution,
        executions=[execution],
    )
    _created, sample_calls, _status_calls = _install_model_stubs(
        monkeypatch,
        collections=[stuck_collection, terminal_collection],
    )

    assert mod.project_completed_collections(limit=1) == 2
    assert stuck_collection.status == "failed"
    assert stuck_collection.reachable is False
    assert "missing" in stuck_collection.error_message
    assert terminal_collection.status == "succeeded"
    assert terminal_collection.reachable is True
    assert sample_calls[0]["unit"] == "pvedaemon.service"
    assert endpoint.service_monitoring_last_success_at == execution.completed_at


def test_project_completed_collections_reachable_false_is_not_projection_error(
    monkeypatch,
):
    mod = _load_rpc_module()
    endpoint = _endpoint()
    collection = _collection(endpoint)
    execution = SimpleNamespace(
        pk=123,
        status="succeeded",
        result={
            "ok": True,
            "procedure": "os.linux.proxmox.show_systemctl_services",
            "target": "pve-01",
            "reachable": False,
            "services": [],
        },
    )
    _install_netbox_rpc_stubs(
        monkeypatch,
        procedure=SimpleNamespace(pk=7),
        execution=execution,
        executions=[execution],
    )
    _created, sample_calls, status_calls = _install_model_stubs(
        monkeypatch,
        collections=[collection],
    )

    assert mod.project_completed_collections() == 1
    assert collection.status == "succeeded"
    assert collection.reachable is False
    assert endpoint.service_monitoring_last_status == "unreachable"
    assert not hasattr(endpoint, "service_monitoring_last_success_at")
    assert sample_calls == []
    assert status_calls == []
