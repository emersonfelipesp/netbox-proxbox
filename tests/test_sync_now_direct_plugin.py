"""Behavior tests for direct plugin-model Sync Now action views."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
from types import SimpleNamespace

import pytest

from tests.conftest import HttpResponseRedirect, load_plugin_module


REPO_ROOT = Path(__file__).resolve().parents[1]


DIRECT_ACTIONS = (
    (
        "backup",
        "VMBackupSyncNowView",
        "_resolve_vm_backup_batch_params",
        "Backup 'backup/vol-100'",
    ),
    (
        "snapshot",
        "VMSnapshotSyncNowView",
        "_resolve_vm_snapshot_batch_params",
        "Snapshot 'before-upgrade'",
    ),
    (
        "task_history",
        "VMTaskHistorySyncNowView",
        "_resolve_task_history_batch_params",
        "Task history 'UPID:pve:100'",
    ),
)


def _install_action_stubs(
    monkeypatch,
    *,
    resolver_name,
    resolver_result,
    scope_result=None,
):
    captured = {}

    individual_sync = types.ModuleType("netbox_proxbox.services.individual_sync")

    def fake_sync(path, query_params, **kwargs):
        captured["sync"] = (path, query_params, kwargs)
        return {"action": "updated"}, 200, ["cluster"]

    individual_sync.sync_individual_with_dependencies = fake_sync
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.services.individual_sync",
        individual_sync,
    )

    branch_lifecycle = types.ModuleType("netbox_proxbox.services.branch_lifecycle")
    branch_lifecycle.get_active_branch_schema_id = lambda: "branch-schema"
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.services.branch_lifecycle",
        branch_lifecycle,
    )

    sync_params = types.ModuleType("netbox_proxbox.sync_params")
    setattr(sync_params, resolver_name, lambda obj: resolver_result)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.sync_params", sync_params)

    endpoint_scope = types.ModuleType("netbox_proxbox.views.sync_now.endpoint_scope")
    resolved_scope = scope_result or (
        {
            "fastapi_endpoint_id": 7,
            "proxmox_endpoint_ids": "71",
        },
        None,
    )
    endpoint_scope.resolve_target_proxmox_endpoint_scope = lambda *args, **kwargs: (
        resolved_scope
    )
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.views.sync_now.endpoint_scope",
        endpoint_scope,
    )

    sync_now = types.ModuleType("netbox_proxbox.views.sync_now")
    sync_now.__path__ = []

    def handle_sync_response(
        request,
        response,
        status,
        dependencies,
        object_label,
        redirect_url,
    ):
        captured["handled"] = (
            response,
            status,
            dependencies,
            object_label,
            redirect_url,
        )
        return HttpResponseRedirect(redirect_url)

    sync_now._handle_sync_response = handle_sync_response
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views.sync_now", sync_now)
    return captured


def _target(pk: int):
    return SimpleNamespace(
        pk=pk,
        volume_id="backup/vol-100",
        name="before-upgrade",
        upid="UPID:pve:100",
        get_absolute_url=lambda: f"/plugins/proxbox/target/{pk}/",
    )


@pytest.mark.parametrize(
    ("module_name", "view_name", "resolver_name", "object_label"),
    DIRECT_ACTIONS,
)
def test_direct_action_uses_resolved_params_and_active_branch(
    monkeypatch,
    module_name,
    view_name,
    resolver_name,
    object_label,
):
    resolver_result = {
        "path": f"sync/individual/{module_name}",
        "query_params": {"pk": 17},
    }
    captured = _install_action_stubs(
        monkeypatch,
        resolver_name=resolver_name,
        resolver_result=resolver_result,
    )
    module = load_plugin_module(
        f"netbox_proxbox.views.sync_now.{module_name}",
        monkeypatch=monkeypatch,
    )
    target = _target(17)
    monkeypatch.setattr(module, "get_object_or_404", lambda *args, **kwargs: target)

    request = SimpleNamespace(user=SimpleNamespace(username="operator"))
    response = getattr(module, view_name)().post(request, pk=17)

    assert response.url == "/plugins/proxbox/target/17/"
    assert captured["sync"] == (
        resolver_result["path"],
        resolver_result["query_params"],
        {
            "netbox_branch_schema_id": "branch-schema",
            "fastapi_endpoint_id": 7,
            "proxmox_endpoint_ids": "71",
        },
    )
    assert captured["handled"] == (
        {"action": "updated"},
        200,
        ["cluster"],
        object_label,
        "/plugins/proxbox/target/17/",
    )


@pytest.mark.parametrize(
    ("module_name", "view_name", "resolver_name", "object_label"),
    DIRECT_ACTIONS,
)
def test_direct_action_with_missing_context_redirects_without_syncing(
    monkeypatch,
    module_name,
    view_name,
    resolver_name,
    object_label,
):
    captured = _install_action_stubs(
        monkeypatch,
        resolver_name=resolver_name,
        resolver_result={"error": "missing context", "status": 422},
    )
    module = load_plugin_module(
        f"netbox_proxbox.views.sync_now.{module_name}",
        monkeypatch=monkeypatch,
    )
    target = _target(23)
    monkeypatch.setattr(module, "get_object_or_404", lambda *args, **kwargs: target)

    request = SimpleNamespace(user=SimpleNamespace(username="operator"))
    response = getattr(module, view_name)().post(request, pk=23)

    assert response.url == "/plugins/proxbox/target/23/"
    assert "sync" not in captured
    assert "handled" not in captured
    assert module._messages_stub.calls
    assert module._messages_stub.calls[-1][0] == "error"


@pytest.mark.parametrize(
    ("module_name", "view_name", "resolver_name", "object_label"),
    DIRECT_ACTIONS,
)
def test_direct_action_with_unresolved_owner_redirects_without_syncing(
    monkeypatch,
    module_name,
    view_name,
    resolver_name,
    object_label,
):
    captured = _install_action_stubs(
        monkeypatch,
        resolver_name=resolver_name,
        resolver_result={
            "path": f"sync/individual/{module_name}",
            "query_params": {"cluster_name": "shared-cluster"},
        },
        scope_result=(None, "The owning Proxmox endpoint is disabled."),
    )
    module = load_plugin_module(
        f"netbox_proxbox.views.sync_now.{module_name}",
        monkeypatch=monkeypatch,
    )
    target = _target(29)
    monkeypatch.setattr(module, "get_object_or_404", lambda *args, **kwargs: target)

    request = SimpleNamespace(user=SimpleNamespace(username="operator"))
    response = getattr(module, view_name)().post(request, pk=29)

    assert response.url == "/plugins/proxbox/target/29/"
    assert "sync" not in captured
    assert "handled" not in captured
    assert module._messages_stub.calls[-1] == (
        "error",
        "The owning Proxmox endpoint is disabled.",
    )


def _load_real_sync_params():
    spec = importlib.util.spec_from_file_location(
        "_sync_now_contract_sync_params",
        REPO_ROOT / "netbox_proxbox" / "sync_params.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_task_history_action_sends_exact_individual_query_contract(monkeypatch):
    """The registered action must use the backend's exact ``type`` contract."""
    captured = _install_action_stubs(
        monkeypatch,
        resolver_name="_resolve_task_history_batch_params",
        resolver_result={"unused": True},
    )
    module = load_plugin_module(
        "netbox_proxbox.views.sync_now.task_history",
        monkeypatch=monkeypatch,
    )
    real_sync_params = _load_real_sync_params()
    monkeypatch.setattr(
        module,
        "_resolve_task_history_batch_params",
        real_sync_params._resolve_task_history_batch_params,
    )

    cluster = SimpleNamespace(pk=41, name="shared-cluster")
    vm = SimpleNamespace(
        cluster=cluster,
        cluster_id=cluster.pk,
        device=SimpleNamespace(name="pve-a"),
        virtual_machine_type=SimpleNamespace(slug="qemu"),
        custom_field_data={"proxmox_vm_id": 100},
    )
    task_history = SimpleNamespace(
        pk=17,
        virtual_machine=vm,
        node="pve-a",
        vm_type="qemu",
        vmid=100,
        upid="UPID:pve-a:100",
        get_absolute_url=lambda: "/plugins/proxbox/task-history/17/",
    )
    monkeypatch.setattr(
        module, "get_object_or_404", lambda *args, **kwargs: task_history
    )

    request = SimpleNamespace(user=SimpleNamespace(username="operator"))
    response = module.VMTaskHistorySyncNowView().post(request, pk=17)

    assert response.url == "/plugins/proxbox/task-history/17/"
    assert captured["sync"] == (
        "sync/individual/task-history",
        {
            "node": "pve-a",
            "type": "qemu",
            "vmid": "100",
            "upid": "UPID:pve-a:100",
            "cluster_name": "shared-cluster",
        },
        {
            "netbox_branch_schema_id": "branch-schema",
            "fastapi_endpoint_id": 7,
            "proxmox_endpoint_ids": "71",
        },
    )


class _TrackingQuerySet:
    def __init__(self, rows):
        self.rows = list(rows)

    def select_related(self, *args):
        return self

    def filter(self, **kwargs):
        rows = self.rows
        if "netbox_cluster_id" in kwargs:
            rows = [
                row
                for row in rows
                if row.netbox_cluster_id == kwargs["netbox_cluster_id"]
            ]
        if "netbox_cluster" in kwargs:
            rows = [
                row for row in rows if row.netbox_cluster is kwargs["netbox_cluster"]
            ]
        return _TrackingQuerySet(rows)

    def first(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


def _tracking_row(*, pk, cluster, endpoint):
    return SimpleNamespace(
        pk=pk,
        name=cluster.name,
        netbox_cluster=cluster,
        netbox_cluster_id=cluster.pk,
        endpoint=endpoint,
    )


def _scope_target(action_name, cluster):
    vm = SimpleNamespace(cluster=cluster, cluster_id=cluster.pk)
    storage = SimpleNamespace(cluster=cluster, cluster_id=cluster.pk)
    if action_name == "backup":
        return SimpleNamespace(proxmox_storage=storage, virtual_machine=vm)
    if action_name == "snapshot":
        return SimpleNamespace(virtual_machine=vm, proxmox_storage=storage)
    return SimpleNamespace(virtual_machine=vm)


def _load_endpoint_scope(monkeypatch, *, backend_ids):
    context = SimpleNamespace(
        endpoint_id=7,
        http_url="https://proxbox.local:8800",
        headers={"X-Proxbox-API-Key": "test-key"},
        verify_ssl=True,
    )
    backend_context = types.ModuleType("netbox_proxbox.services.backend_context")
    backend_context.get_fastapi_request_context = lambda: context
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.services.backend_context",
        backend_context,
    )

    captured = {"resolved": []}
    backend_sync = types.ModuleType("netbox_proxbox.views.backend_sync")

    def resolve_backend_endpoint_id(endpoint, **kwargs):
        captured["resolved"].append((endpoint, kwargs))
        return backend_ids[endpoint.pk], None

    backend_sync.resolve_backend_endpoint_id = resolve_backend_endpoint_id
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.views.backend_sync",
        backend_sync,
    )

    module = load_plugin_module(
        "netbox_proxbox.views.sync_now.endpoint_scope",
        monkeypatch=monkeypatch,
    )
    return module, captured


@pytest.mark.parametrize("action_name", ("backup", "snapshot", "task_history"))
def test_direct_action_scope_uses_linked_cluster_not_duplicate_name(
    monkeypatch, action_name
):
    """A same-named cluster on another estate must never enter the scope."""
    module, captured = _load_endpoint_scope(monkeypatch, backend_ids={1: 101, 2: 202})
    cluster_a = SimpleNamespace(pk=41, name="shared-cluster")
    cluster_b = SimpleNamespace(pk=42, name="shared-cluster")
    endpoint_a = SimpleNamespace(pk=1, name="pve-a", enabled=True)
    endpoint_b = SimpleNamespace(pk=2, name="pve-b", enabled=True)
    module.ProxmoxCluster.objects = _TrackingQuerySet(
        [
            _tracking_row(pk=1, cluster=cluster_a, endpoint=endpoint_a),
            _tracking_row(pk=2, cluster=cluster_b, endpoint=endpoint_b),
        ]
    )

    scope, error = module.resolve_target_proxmox_endpoint_scope(
        _scope_target(action_name, cluster_a),
        prefer_storage=action_name == "backup",
    )

    assert error is None
    assert scope == {
        "fastapi_endpoint_id": 7,
        "proxmox_endpoint_ids": "101",
    }
    assert [endpoint.pk for endpoint, _ in captured["resolved"]] == [1]


@pytest.mark.parametrize("action_name", ("backup", "snapshot", "task_history"))
def test_direct_action_scope_refuses_disabled_owner_without_sync(
    monkeypatch, action_name
):
    """A disabled owner stays unusable even if the backend still holds it."""
    module, captured = _load_endpoint_scope(monkeypatch, backend_ids={1: 101, 2: 202})
    cluster_a = SimpleNamespace(pk=41, name="shared-cluster")
    cluster_b = SimpleNamespace(pk=42, name="shared-cluster")
    endpoint_a = SimpleNamespace(pk=1, name="pve-a", enabled=False)
    endpoint_b = SimpleNamespace(pk=2, name="pve-b", enabled=True)
    module.ProxmoxCluster.objects = _TrackingQuerySet(
        [
            _tracking_row(pk=1, cluster=cluster_a, endpoint=endpoint_a),
            _tracking_row(pk=2, cluster=cluster_b, endpoint=endpoint_b),
        ]
    )

    scope, error = module.resolve_target_proxmox_endpoint_scope(
        _scope_target(action_name, cluster_a),
        prefer_storage=action_name == "backup",
    )

    assert scope is None
    assert "disabled" in str(error).lower()
    assert captured["resolved"] == []


@pytest.mark.parametrize("action_name", ("backup", "snapshot", "task_history"))
def test_direct_action_scope_refuses_ambiguous_enabled_owners(monkeypatch, action_name):
    module, captured = _load_endpoint_scope(monkeypatch, backend_ids={1: 101, 2: 202})
    cluster = SimpleNamespace(pk=41, name="shared-cluster")
    endpoint_a = SimpleNamespace(pk=1, name="pve-a", enabled=True)
    endpoint_b = SimpleNamespace(pk=2, name="pve-b", enabled=True)
    module.ProxmoxCluster.objects = _TrackingQuerySet(
        [
            _tracking_row(pk=1, cluster=cluster, endpoint=endpoint_a),
            _tracking_row(pk=2, cluster=cluster, endpoint=endpoint_b),
        ]
    )

    scope, error = module.resolve_target_proxmox_endpoint_scope(
        _scope_target(action_name, cluster),
        prefer_storage=action_name == "backup",
    )

    assert scope is None
    assert "more than one enabled" in str(error).lower()
    assert captured["resolved"] == []


@pytest.mark.parametrize("action_name", ("backup", "snapshot", "task_history"))
def test_direct_action_scope_refuses_missing_tracking(monkeypatch, action_name):
    module, captured = _load_endpoint_scope(monkeypatch, backend_ids={})
    cluster = SimpleNamespace(pk=41, name="untracked-cluster")
    module.ProxmoxCluster.objects = _TrackingQuerySet([])

    scope, error = module.resolve_target_proxmox_endpoint_scope(
        _scope_target(action_name, cluster),
        prefer_storage=action_name == "backup",
    )

    assert scope is None
    assert "not linked" in str(error).lower()
    assert captured["resolved"] == []


def _load_sync_now_init(monkeypatch):
    _install_action_stubs(
        monkeypatch,
        resolver_name="_resolve_vm_backup_batch_params",
        resolver_result={"error": "unused"},
    )
    load_plugin_module(
        "netbox_proxbox.views.sync_now.backup",
        monkeypatch=monkeypatch,
    )
    spec = importlib.util.spec_from_file_location(
        "_sync_now_response_under_test",
        REPO_ROOT / "netbox_proxbox" / "views" / "sync_now" / "__init__.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shared_response_handler_treats_http_200_error_payload_as_failure(monkeypatch):
    module = _load_sync_now_init(monkeypatch)
    response = module._handle_sync_response(
        SimpleNamespace(),
        {"error": "No Proxmox session matches this object."},
        200,
        [],
        "Backup 'backup/vol-100'",
        "/plugins/proxbox/backup/17/",
    )

    assert response.url == "/plugins/proxbox/backup/17/"
    assert module.messages.calls == [
        (
            "error",
            "Failed to sync backup 'backup/vol-100': "
            "No Proxmox session matches this object.",
        )
    ]
