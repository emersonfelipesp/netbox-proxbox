"""Branch and endpoint isolation contracts for create-instance sync-back."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from tests.test_endpoint_create_instance import _load_create_view


def test_created_instance_sync_transport_carries_branch_and_endpoint_scopes(
    monkeypatch,
):
    module = _load_create_view(monkeypatch)
    calls: list[tuple[object, object, dict[str, object]]] = []

    def sync_individual(path, query_params, **kwargs):
        calls.append((path, query_params, kwargs))
        return {"action": "created"}, 200

    branch_lifecycle = sys.modules["netbox_proxbox.services.branch_lifecycle"]
    branch_lifecycle.require_active_branch_schema_id = lambda decision: (
        "branch-schema-325"
    )
    monkeypatch.setattr(module, "sync_individual", sync_individual)

    note = module._sync_created_instance(
        endpoint=SimpleNamespace(pk=5),
        request=SimpleNamespace(),
        cluster_name="cluster-a",
        target_node="node-a",
        vm_type="qemu",
        new_vmid=120,
        fastapi_endpoint_id=9,
        backend_endpoint_id=77,
    )

    assert note is None
    assert calls == [
        (
            "sync/individual/vm",
            {
                "cluster_name": "cluster-a",
                "node": "node-a",
                "type": "qemu",
                "vmid": 120,
            },
            {
                "netbox_branch_schema_id": "branch-schema-325",
                "fastapi_endpoint_id": 9,
                "proxmox_endpoint_ids": "77",
            },
        )
    ]


def test_created_instance_sync_fails_closed_when_isolation_is_unavailable(
    monkeypatch,
):
    module = _load_create_view(monkeypatch)
    branch_lifecycle = sys.modules["netbox_proxbox.services.branch_lifecycle"]

    def sync_call(*args, **kwargs):
        pytest.fail("unguarded sync transport ran")

    def refuse_isolation():
        raise RuntimeError("branch isolation unavailable")

    branch_lifecycle.require_branch_isolation_or_raise = refuse_isolation
    monkeypatch.setattr(module, "sync_individual", sync_call)

    note = module._sync_created_instance(
        endpoint=SimpleNamespace(pk=5),
        request=SimpleNamespace(),
        cluster_name="cluster-a",
        target_node="node-a",
        vm_type="qemu",
        new_vmid=120,
        fastapi_endpoint_id=9,
        backend_endpoint_id=77,
    )

    assert note == "Created instance sync is pending: branch isolation unavailable"


def test_create_instance_rejects_enabled_isolation_without_active_branch(
    monkeypatch,
):
    """The request must stop with 409 before any backend transport runs."""
    module = _load_create_view(monkeypatch)
    branch_lifecycle = sys.modules["netbox_proxbox.services.branch_lifecycle"]
    branch_lifecycle.require_branch_isolation_or_raise = lambda: SimpleNamespace(
        state="enabled"
    )

    def require_active_branch(decision):
        del decision
        raise branch_lifecycle.ActiveBranchRequiredError(
            "Proxbox sync refused: branch isolation is enabled, but this request "
            "has no active READY branch schema; activate a branch or disable "
            "branch isolation."
        )

    branch_lifecycle.require_active_branch_schema_id = require_active_branch
    endpoint = SimpleNamespace(pk=5, allow_writes=True)
    monkeypatch.setattr(module, "get_object_or_404", lambda *args, **kwargs: endpoint)
    backend_context = pytest.fail
    monkeypatch.setattr(module, "get_fastapi_request_context", backend_context)
    monkeypatch.setattr(module.requests, "post", pytest.fail)
    request = SimpleNamespace(user=SimpleNamespace(username="operator"), body=b"{}")

    response = module.ProxmoxEndpointCreateInstanceView().post(request, pk=5)

    assert response.status_code == 409
    assert response.payload["reason"] == "active_branch_required"
    assert "activate a branch or disable branch isolation" in response.payload["detail"]
