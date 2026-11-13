"""Pure decision tests for native-corroborated VM relation resolution."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def resolver(monkeypatch):
    """Load the resolver with its real endpoint-claim authority helpers."""
    sync_state = types.ModuleType("netbox_proxbox.models.sync_state")
    sync_state.ProxboxVirtualMachineSyncState = type(
        "ProxboxVirtualMachineSyncState", (), {}
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models.sync_state", sync_state)

    backfill_name = "netbox_proxbox.services.sync_state_endpoint_backfill"
    backfill_spec = importlib.util.spec_from_file_location(
        backfill_name,
        REPO_ROOT / "netbox_proxbox" / "services" / "sync_state_endpoint_backfill.py",
    )
    assert backfill_spec is not None and backfill_spec.loader is not None
    backfill = importlib.util.module_from_spec(backfill_spec)
    monkeypatch.setitem(sys.modules, backfill_name, backfill)
    backfill_spec.loader.exec_module(backfill)

    module_name = "netbox_proxbox.services.sync_state_relation_resolver"
    spec = importlib.util.spec_from_file_location(
        module_name,
        REPO_ROOT / "netbox_proxbox" / "services" / "sync_state_relation_resolver.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


def _row(resolver, **overrides):
    values = {
        "pk": 41,
        "virtual_machine_id": 501,
        "endpoint_id": None,
        "backend_id": 14,
        "node_id": None,
        "node_name": "pve-a",
        "cluster_id": None,
        "cluster_name": "cluster-a",
        "native_cluster_id": 301,
        "native_device_id": None,
    }
    values.update(overrides)
    return resolver.SyncStateIdentity(**values)


def _endpoint(resolver, pk=5, native_cluster_id=301):
    return resolver.EndpointRecord(pk=pk, native_cluster_id=native_cluster_id)


def _cluster(resolver, pk=101, endpoint_id=5, name="cluster-a", native_cluster_id=301):
    return resolver.ClusterRecord(
        pk=pk,
        endpoint_id=endpoint_id,
        name=name,
        native_cluster_id=native_cluster_id,
    )


def _node(
    resolver,
    pk=201,
    endpoint_id=5,
    name="pve-a",
    cluster_id=101,
    native_device_id=None,
):
    return resolver.NodeRecord(
        pk=pk,
        endpoint_id=endpoint_id,
        name=name,
        cluster_id=cluster_id,
        native_device_id=native_device_id,
    )


def _plan(resolver, row=None, *, endpoints=None, nodes=None, clusters=None):
    return resolver.plan_sync_state_relation_update(
        row or _row(resolver),
        plugin_endpoint_id=5,
        endpoint_records=endpoints or [_endpoint(resolver)],
        node_records=nodes or [],
        cluster_records=clusters or [],
    )


def test_unique_names_bind_endpoint_node_and_cluster(resolver):
    plan = _plan(
        resolver,
        nodes=[_node(resolver)],
        clusters=[_cluster(resolver)],
    )

    assert plan.updates == {
        "endpoint_id": 5,
        "proxmox_cluster_id": 101,
        "proxmox_node_id": 201,
    }
    assert plan.reasons == ()
    assert plan.node_action == "bound"
    assert plan.cluster_action == "bound"


def test_zero_name_match_leaves_relations_unbound(resolver):
    plan = _plan(resolver)

    assert plan.updates == {"endpoint_id": 5}
    assert plan.reasons == ("cluster_not_found", "node_not_found")


def test_multiple_name_matches_are_ambiguous_and_never_guess(resolver):
    plan = _plan(
        resolver,
        row=_row(resolver, cluster_name=""),
        nodes=[
            _node(resolver, pk=201, cluster_id=None),
            _node(resolver, pk=202, cluster_id=None),
        ],
    )

    assert plan.updates == {"endpoint_id": 5}
    assert plan.reasons == ("cluster_name_missing", "node_ambiguous")


def test_same_node_name_on_another_endpoint_is_not_a_match(resolver):
    plan = _plan(
        resolver,
        nodes=[
            _node(resolver, pk=201, endpoint_id=6),
            _node(resolver, pk=202),
        ],
        clusters=[_cluster(resolver)],
    )

    assert plan.updates == {
        "endpoint_id": 5,
        "proxmox_cluster_id": 101,
        "proxmox_node_id": 202,
    }
    assert plan.reasons == ()


def test_ambiguous_backend_id_claim_is_refused(resolver):
    scope, skipped = resolver.current_run_endpoint_scope({"5": "14", "6": "14"})

    assert scope == {}
    assert skipped == {"14": "claimed by multiple ProxmoxEndpoint primary keys: 5, 6"}


@pytest.mark.parametrize(
    ("row", "nodes", "clusters"),
    [
        (
            {"endpoint_id": 6},
            [(201, 5, "pve-a", 101, None)],
            [(101, 5, "cluster-a", 301)],
        ),
        (
            {"node_id": 299},
            [(299, 6, "pve-a", 101, None), (201, 5, "pve-a", 101, None)],
            [(101, 5, "cluster-a", 301)],
        ),
        (
            {"cluster_id": 199},
            [(201, 5, "pve-a", 101, None)],
            [(199, 6, "cluster-a", None), (101, 5, "cluster-a", 301)],
        ),
    ],
)
def test_present_relation_or_endpoint_disagreement_refuses_every_update(
    resolver, row, nodes, clusters
):
    plan = _plan(
        resolver,
        row=_row(resolver, **row),
        nodes=[_node(resolver, *record) for record in nodes],
        clusters=[_cluster(resolver, *record) for record in clusters],
    )

    assert plan.updates == {}
    assert plan.reasons == ("relations_disagree",)


def test_native_device_and_recorded_name_rebind_node_after_migration(resolver):
    plan = _plan(
        resolver,
        row=_row(
            resolver,
            endpoint_id=5,
            node_id=201,
            cluster_id=101,
            native_device_id=402,
        ),
        nodes=[
            _node(resolver, pk=201, name="pve-old", native_device_id=401),
            _node(resolver, pk=202, native_device_id=402),
        ],
        clusters=[_cluster(resolver)],
    )

    assert plan.updates == {"proxmox_node_id": 202}
    assert plan.reasons == ()
    assert plan.node_action == "rebound"


def test_second_resolution_is_idempotent(resolver):
    nodes = [_node(resolver)]
    clusters = [_cluster(resolver)]
    first = _plan(resolver, nodes=nodes, clusters=clusters)
    second = _plan(
        resolver,
        row=_row(
            resolver,
            endpoint_id=5,
            node_id=201,
            cluster_id=101,
        ),
        nodes=nodes,
        clusters=clusters,
    )

    assert first.updates == {
        "endpoint_id": 5,
        "proxmox_cluster_id": 101,
        "proxmox_node_id": 201,
    }
    assert second.updates == {}
    assert second.reasons == ()


def test_stamped_backend_identity_refused_when_native_cluster_has_another_owner(
    resolver,
):
    plan = _plan(
        resolver,
        endpoints=[
            _endpoint(resolver, pk=5, native_cluster_id=302),
            _endpoint(resolver, pk=6, native_cluster_id=301),
        ],
        nodes=[_node(resolver)],
        clusters=[_cluster(resolver, endpoint_id=6)],
    )

    assert plan.updates == {}
    assert plan.reasons == ("native_cluster_ownership_ambiguous",)


def test_vm_without_native_cluster_is_refused(resolver):
    plan = _plan(
        resolver,
        row=_row(resolver, native_cluster_id=None),
        nodes=[_node(resolver)],
        clusters=[_cluster(resolver)],
    )

    assert plan.updates == {}
    assert plan.reasons == ("native_cluster_missing",)


def test_native_cluster_claimed_by_two_endpoints_is_refused(resolver):
    plan = _plan(
        resolver,
        endpoints=[_endpoint(resolver)],
        clusters=[
            _cluster(resolver),
            _cluster(resolver, pk=102, endpoint_id=6, name="foreign-cluster"),
        ],
    )

    assert plan.updates == {}
    assert plan.reasons == ("native_cluster_ownership_ambiguous",)


def test_native_link_binds_cluster_when_recorded_name_is_stale(resolver):
    plan = _plan(
        resolver,
        row=_row(resolver, cluster_name="stale-cluster-name", node_name=""),
        clusters=[_cluster(resolver, name="current-cluster-name")],
    )

    assert plan.updates == {"endpoint_id": 5, "proxmox_cluster_id": 101}
    assert plan.reasons == ("node_name_missing",)


def test_name_resolved_cluster_disagreeing_with_native_link_is_refused(resolver):
    plan = _plan(
        resolver,
        row=_row(resolver, cluster_name="stale-target", node_name=""),
        clusters=[
            _cluster(resolver, name="current-cluster"),
            _cluster(
                resolver,
                pk=102,
                name="stale-target",
                native_cluster_id=None,
            ),
        ],
    )

    assert plan.updates == {"endpoint_id": 5}
    assert plan.reasons == (
        "cluster_name_contradicts_native_link",
        "node_name_missing",
    )


def test_node_whose_cluster_disagrees_is_refused(resolver):
    plan = _plan(
        resolver,
        row=_row(resolver, native_device_id=401),
        nodes=[_node(resolver, cluster_id=102, native_device_id=401)],
        clusters=[_cluster(resolver)],
    )

    assert plan.updates == {"endpoint_id": 5, "proxmox_cluster_id": 101}
    assert plan.reasons == ("node_contradicts_cluster",)


def test_vm_native_device_without_linked_endpoint_node_is_refused(resolver):
    plan = _plan(
        resolver,
        row=_row(resolver, native_device_id=401),
        nodes=[_node(resolver, native_device_id=None)],
        clusters=[_cluster(resolver)],
    )

    assert plan.updates == {"endpoint_id": 5, "proxmox_cluster_id": 101}
    assert plan.reasons == ("node_native_device_not_found",)


def test_multiple_nodes_linked_to_vm_native_device_are_refused(resolver):
    plan = _plan(
        resolver,
        row=_row(resolver, native_device_id=401),
        nodes=[
            _node(resolver, pk=201, native_device_id=401),
            _node(resolver, pk=202, name="pve-b", native_device_id=401),
        ],
        clusters=[_cluster(resolver)],
    )

    assert plan.updates == {"endpoint_id": 5, "proxmox_cluster_id": 101}
    assert plan.reasons == ("node_native_device_ambiguous",)


def test_vm_without_native_device_binds_null_node_from_unique_name(resolver):
    plan = _plan(
        resolver,
        row=_row(resolver, native_device_id=None),
        nodes=[_node(resolver, native_device_id=402)],
        clusters=[_cluster(resolver)],
    )

    assert plan.updates == {
        "endpoint_id": 5,
        "proxmox_cluster_id": 101,
        "proxmox_node_id": 201,
    }
    assert plan.reasons == ()


def test_vm_without_native_device_preserves_existing_node_on_name_drift(resolver):
    plan = _plan(
        resolver,
        row=_row(
            resolver,
            endpoint_id=5,
            node_id=202,
            cluster_id=101,
            native_device_id=None,
        ),
        nodes=[
            _node(resolver, pk=201, native_device_id=None),
            _node(resolver, pk=202, name="pve-current", native_device_id=None),
        ],
        clusters=[_cluster(resolver)],
    )

    assert plan.updates == {}
    assert plan.reasons == ("node_unverified_drift_without_native_device",)
    assert plan.node_action is None


def test_native_device_preserves_correct_node_when_recorded_name_is_stale(resolver):
    plan = _plan(
        resolver,
        row=_row(
            resolver,
            endpoint_id=5,
            node_id=202,
            cluster_id=101,
            native_device_id=401,
        ),
        nodes=[
            _node(resolver, pk=201, native_device_id=None),
            _node(resolver, pk=202, name="pve-current", native_device_id=401),
        ],
        clusters=[_cluster(resolver)],
    )

    assert plan.updates == {}
    assert plan.reasons == ("node_name_contradicts_native_device",)
    assert plan.node_action is None


def test_native_device_refuses_stale_name_when_node_relation_is_null(resolver):
    plan = _plan(
        resolver,
        row=_row(resolver, native_device_id=401),
        nodes=[
            _node(resolver, pk=201, native_device_id=None),
            _node(resolver, pk=202, name="pve-current", native_device_id=401),
        ],
        clusters=[_cluster(resolver)],
    )

    assert plan.updates == {"endpoint_id": 5, "proxmox_cluster_id": 101}
    assert plan.reasons == ("node_name_contradicts_native_device",)
    assert plan.node_action is None


def test_native_device_and_recorded_name_bind_the_same_node(resolver):
    plan = _plan(
        resolver,
        row=_row(resolver, native_device_id=401),
        nodes=[_node(resolver, native_device_id=401)],
        clusters=[_cluster(resolver)],
    )

    assert plan.updates == {
        "endpoint_id": 5,
        "proxmox_cluster_id": 101,
        "proxmox_node_id": 201,
    }
    assert plan.reasons == ()
    assert plan.node_action == "bound"
