"""Behavior tests for direct plugin-model Sync Now action views."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

from tests.conftest import HttpResponseRedirect, load_plugin_module


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


def _install_action_stubs(monkeypatch, *, resolver_name, resolver_result):
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
        {"netbox_branch_schema_id": "branch-schema"},
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
