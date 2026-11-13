"""Real-ORM coverage for corroborated sync-state endpoint backfill."""

from __future__ import annotations

import os

import pytest

_REQUIRE_DJANGO = os.environ.get("NETBOX_PROXBOX_REQUIRE_DJANGO", "").lower() in (
    "1",
    "true",
    "yes",
)

try:
    import django
except ModuleNotFoundError:
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        "Django/NetBox test dependencies are not installed in this environment.",
        allow_module_level=True,
    )

if not hasattr(django, "__path__"):
    pytest.skip(
        "The mocked suite does not provide a real Django package.",
        allow_module_level=True,
    )

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:  # pragma: no cover - external test harness availability
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is not available: {exc}",
        allow_module_level=True,
    )

from dcim.models import (  # noqa: E402
    Device,
    DeviceRole,
    DeviceType,
    Manufacturer,
    Site,
)
from virtualization.models import Cluster, ClusterType, VirtualMachine  # noqa: E402

from netbox_proxbox.models import (  # noqa: E402
    ProxboxVirtualMachineSyncState,
    ProxmoxCluster,
    ProxmoxEndpoint,
    ProxmoxNode,
)
from netbox_proxbox.services.sync_state_endpoint_backfill import (  # noqa: E402
    backfill_sync_state_endpoints,
    preview_sync_state_endpoint_backfill,
)
from netbox_proxbox.services.sync_state_relation_resolver import (  # noqa: E402
    resolve_current_run_vm_sync_state_relations,
)
from netbox_proxbox.services.vm_console import resolve_console_identity  # noqa: E402


def _state(
    name: str,
    raw_id: int,
    *,
    vm_cluster: Cluster | None = None,
    vm_device: Device | None = None,
    **relations,
) -> ProxboxVirtualMachineSyncState:
    vm = VirtualMachine.objects.create(
        name=name,
        status="active",
        cluster=vm_cluster,
        device=vm_device,
    )
    return ProxboxVirtualMachineSyncState.objects.create(
        virtual_machine=vm,
        proxmox_endpoint_raw_id=raw_id,
        **relations,
    )


def _owned_cluster(prefix: str) -> tuple[ProxmoxEndpoint, Cluster, ProxmoxCluster]:
    cluster_type = ClusterType.objects.create(name=prefix, slug=prefix)
    native = Cluster.objects.create(name=f"{prefix}-native", type=cluster_type)
    endpoint = ProxmoxEndpoint.objects.create(name=f"{prefix}-endpoint", enabled=True)
    ProxmoxEndpoint.objects.filter(pk=endpoint.pk).update(netbox_cluster=native)
    endpoint.refresh_from_db()
    tracking = ProxmoxCluster.objects.bulk_create(
        [
            ProxmoxCluster(
                endpoint=endpoint,
                netbox_cluster=native,
                name=f"{prefix}-tracking",
            )
        ]
    )[0]
    return endpoint, native, tracking


def _device(name: str) -> Device:
    site = Site.objects.create(name=f"{name}-site", slug=f"{name}-site")
    manufacturer = Manufacturer.objects.create(
        name=f"{name}-manufacturer",
        slug=f"{name}-manufacturer",
    )
    device_type = DeviceType.objects.create(
        manufacturer=manufacturer,
        model=f"{name}-type",
        slug=f"{name}-type",
    )
    role = DeviceRole.objects.create(name=f"{name}-role", slug=f"{name}-role")
    return Device.objects.create(
        name=name,
        site=site,
        device_type=device_type,
        role=role,
    )


@pytest.mark.django_db
def test_real_orm_binds_only_rows_corroborated_by_their_own_inventory():
    mapped_endpoint = ProxmoxEndpoint.objects.create(name="backfill-mapped")
    other_endpoint = ProxmoxEndpoint.objects.create(name="backfill-other")
    mapped_cluster = ProxmoxCluster.objects.create(
        endpoint=mapped_endpoint,
        name="backfill-unique-cluster",
    )
    other_cluster = ProxmoxCluster.objects.create(
        endpoint=other_endpoint,
        name="backfill-other-cluster",
    )
    shared_name = "backfill-shared-cluster"
    ProxmoxCluster.objects.create(endpoint=mapped_endpoint, name=shared_name)
    ProxmoxCluster.objects.create(endpoint=other_endpoint, name=shared_name)
    mapped_node = ProxmoxNode.objects.create(
        endpoint=mapped_endpoint,
        proxmox_cluster=mapped_cluster,
        name="backfill-mapped-node",
        ip_address="2001:db8::40",
    )
    other_node = ProxmoxNode.objects.create(
        endpoint=other_endpoint,
        proxmox_cluster=other_cluster,
        name="backfill-other-node",
        ip_address="2001:db8::41",
    )

    by_cluster = _state(
        "backfill-by-cluster",
        14,
        proxmox_cluster=mapped_cluster,
    )
    by_node = _state("backfill-by-node", 14, proxmox_node=mapped_node)
    by_name = _state(
        "backfill-by-name",
        14,
        proxmox_cluster_name=mapped_cluster.name,
    )
    contradicted = _state(
        "backfill-contradicted",
        14,
        proxmox_cluster=other_cluster,
    )
    uncorroborated = _state(
        "backfill-uncorroborated",
        14,
        proxmox_cluster_name="backfill-missing-cluster",
    )
    ambiguous_name = _state(
        "backfill-ambiguous-name",
        14,
        proxmox_cluster_name=shared_name,
    )
    cluster_matches_node_contradicts = _state(
        "backfill-cluster-matches-node-contradicts",
        14,
        proxmox_cluster=mapped_cluster,
        proxmox_node=other_node,
    )
    node_matches_cluster_contradicts = _state(
        "backfill-node-matches-cluster-contradicts",
        14,
        proxmox_cluster=other_cluster,
        proxmox_node=mapped_node,
    )

    summary = backfill_sync_state_endpoints({str(mapped_endpoint.pk): "14"})

    bound = ProxboxVirtualMachineSyncState.objects.filter(
        pk__in=[by_cluster.pk, by_node.pk],
        endpoint=mapped_endpoint,
    )
    assert bound.count() == 2
    assert (
        ProxboxVirtualMachineSyncState.objects.filter(
            pk__in=[
                by_name.pk,
                contradicted.pk,
                uncorroborated.pk,
                ambiguous_name.pk,
                cluster_matches_node_contradicts.pk,
                node_matches_cluster_contradicts.pk,
            ],
            endpoint__isnull=True,
        ).count()
        == 6
    )
    bucket = summary.unverified[f"14={mapped_endpoint.pk}"]
    assert bucket["count"] == 6
    assert bucket["sample_pks"] == [
        by_name.pk,
        contradicted.pk,
        uncorroborated.pk,
        ambiguous_name.pk,
        cluster_matches_node_contradicts.pk,
        node_matches_cluster_contradicts.pk,
    ]
    assert bucket["reasons"]["relations_disagree"] == {
        "count": 2,
        "sample_pks": [
            cluster_matches_node_contradicts.pk,
            node_matches_cluster_contradicts.pk,
        ],
        "sample_rows": [
            {
                "pk": cluster_matches_node_contradicts.pk,
                "proxmox_cluster_name": "",
            },
            {
                "pk": node_matches_cluster_contradicts.pk,
                "proxmox_cluster_name": "",
            },
        ],
    }
    assert bucket["reasons"]["no_relation_evidence"] == {
        "count": 3,
        "sample_pks": [by_name.pk, uncorroborated.pk, ambiguous_name.pk],
        "sample_rows": [
            {
                "pk": by_name.pk,
                "proxmox_cluster_name": mapped_cluster.name,
            },
            {
                "pk": uncorroborated.pk,
                "proxmox_cluster_name": "backfill-missing-cluster",
            },
            {
                "pk": ambiguous_name.pk,
                "proxmox_cluster_name": shared_name,
            },
        ],
    }
    assert summary.total_rows_bound == 2
    assert summary.total_unverified == 6


@pytest.mark.django_db
def test_real_orm_name_only_row_requires_confirmed_review_token():
    first_endpoint = ProxmoxEndpoint.objects.create(name="backfill-confirmed")
    second_endpoint = ProxmoxEndpoint.objects.create(name="backfill-not-confirmed")
    matching_cluster = ProxmoxCluster.objects.create(
        endpoint=first_endpoint,
        name="backfill-confirmed-cluster",
    )
    confirmed = _state(
        "backfill-confirmed-row",
        14,
        proxmox_cluster_name=matching_cluster.name,
    )
    left_unbound = _state("backfill-unconfirmed-row", 15)
    mapping = {str(first_endpoint.pk): "14", str(second_endpoint.pk): "15"}

    automatic = backfill_sync_state_endpoints(mapping)

    confirmed.refresh_from_db()
    assert confirmed.endpoint_id is None
    assert automatic.unverified[f"14={first_endpoint.pk}"]["reasons"][
        "no_relation_evidence"
    ]["sample_rows"] == [
        {
            "pk": confirmed.pk,
            "proxmox_cluster_name": matching_cluster.name,
        }
    ]

    preview = preview_sync_state_endpoint_backfill(
        mapping,
        confirmed_bindings={"14": str(first_endpoint.pk)},
    )
    token = preview.confirmed_bindings[f"14={first_endpoint.pk}"]["review_token"]

    summary = backfill_sync_state_endpoints(
        mapping,
        confirmed_bindings={"14": str(first_endpoint.pk)},
        confirmation_review_tokens={"14": token},
    )

    confirmed.refresh_from_db()
    left_unbound.refresh_from_db()
    assert confirmed.endpoint_id == first_endpoint.pk
    assert left_unbound.endpoint_id is None
    assert summary.confirmed_bindings[f"14={first_endpoint.pk}"]["row_pks"] == [
        confirmed.pk
    ]
    assert summary.unverified[f"15={second_endpoint.pk}"]["sample_pks"] == [
        left_unbound.pk
    ]


@pytest.mark.django_db
def test_current_run_relation_resolver_binds_null_relations_for_console_identity():
    endpoint, native_cluster, cluster = _owned_cluster("current-run-console")
    native_device = _device("current-run-console-device")
    node = ProxmoxNode.objects.create(
        endpoint=endpoint,
        proxmox_cluster=cluster,
        netbox_device=native_device,
        name="current-run-console-node",
        ip_address="2001:db8::80",
    )
    current = _state(
        "current-run-console-vm",
        14,
        last_run_id="run-current-console",
        proxmox_node_name=node.name,
        proxmox_cluster_name="stale-cluster-name",
        proxmox_vm_id=280,
        proxmox_vm_type="qemu",
        vm_cluster=native_cluster,
        vm_device=native_device,
    )
    historical = _state(
        "historical-console-vm",
        14,
        last_run_id="run-historical-console",
        proxmox_node_name=node.name,
        proxmox_cluster_name=cluster.name,
        proxmox_vm_id=279,
        proxmox_vm_type="qemu",
        vm_cluster=native_cluster,
        vm_device=native_device,
    )

    summary = resolve_current_run_vm_sync_state_relations(
        {str(endpoint.pk): "14"},
        run_id="run-current-console",
    )

    current.refresh_from_db()
    historical.refresh_from_db()
    assert current.endpoint_id == endpoint.pk
    assert current.proxmox_node_id == node.pk
    assert current.proxmox_cluster_id == cluster.pk
    assert historical.endpoint_id is None
    assert historical.proxmox_node_id is None
    assert historical.proxmox_cluster_id is None
    assert summary.as_dict() == {
        "rows_examined": 1,
        "rows_changed": 1,
        "endpoints_bound": 1,
        "nodes_bound": 1,
        "nodes_rebound": 0,
        "clusters_bound": 1,
        "clusters_rebound": 0,
        "skipped_backend_ids": {},
        "unresolved": {},
        "rows_with_unresolved_relations": 0,
    }

    vm = VirtualMachine.objects.get(pk=current.virtual_machine_id)
    identity = resolve_console_identity(vm)
    assert identity.virtual_machine_id == vm.pk
    assert identity.endpoint.pk == endpoint.pk
    assert identity.vmid == 280
    assert identity.node == "current-run-console-node"
    assert identity.vm_type == "qemu"
    assert identity.backend_raw_id == 14


@pytest.mark.django_db
def test_current_run_relation_resolver_repairs_node_drift_and_is_idempotent():
    endpoint, native_cluster, cluster = _owned_cluster("current-run-drift")
    old_device = _device("current-run-old-device")
    new_device = _device("current-run-new-device")
    old_node = ProxmoxNode.objects.create(
        endpoint=endpoint,
        proxmox_cluster=cluster,
        netbox_device=old_device,
        name="current-run-old-node",
        ip_address="2001:db8::81",
    )
    new_node = ProxmoxNode.objects.create(
        endpoint=endpoint,
        proxmox_cluster=cluster,
        netbox_device=new_device,
        name="current-run-new-node",
        ip_address="2001:db8::82",
    )
    state = _state(
        "current-run-drift-vm",
        15,
        last_run_id="run-current-drift",
        endpoint=endpoint,
        proxmox_node=old_node,
        proxmox_node_name=new_node.name,
        proxmox_cluster=cluster,
        proxmox_cluster_name=cluster.name,
        proxmox_vm_id=281,
        proxmox_vm_type="qemu",
        vm_cluster=native_cluster,
        vm_device=new_device,
    )
    mapping = {str(endpoint.pk): "15"}

    first = resolve_current_run_vm_sync_state_relations(
        mapping,
        run_id="run-current-drift",
    )
    second = resolve_current_run_vm_sync_state_relations(
        mapping,
        run_id="run-current-drift",
    )

    state.refresh_from_db()
    assert state.proxmox_node_id == new_node.pk
    assert first.rows_changed == 1
    assert first.nodes_rebound == 1
    assert second.rows_examined == 1
    assert second.rows_changed == 0
    assert second.nodes_rebound == 0

    identity = resolve_console_identity(state.virtual_machine)
    assert identity.endpoint.pk == endpoint.pk
    assert identity.node == "current-run-new-node"
    assert identity.vmid == 281


@pytest.mark.django_db
def test_current_run_relation_resolver_preserves_node_on_stale_name_with_device():
    endpoint, native_cluster, cluster = _owned_cluster("stale-name-device")
    correct_device = _device("stale-name-correct-device")
    stale_device = _device("stale-name-old-device")
    correct_node = ProxmoxNode.objects.create(
        endpoint=endpoint,
        proxmox_cluster=cluster,
        netbox_device=correct_device,
        name="stale-name-current-node",
        ip_address="2001:db8::85",
    )
    stale_node = ProxmoxNode.objects.create(
        endpoint=endpoint,
        proxmox_cluster=cluster,
        netbox_device=stale_device,
        name="stale-name-old-node",
        ip_address="2001:db8::86",
    )
    state = _state(
        "stale-name-device-vm",
        18,
        last_run_id="run-stale-name-device",
        endpoint=endpoint,
        proxmox_node=correct_node,
        proxmox_node_name=stale_node.name,
        proxmox_cluster=cluster,
        proxmox_cluster_name=cluster.name,
        vm_cluster=native_cluster,
        vm_device=correct_device,
    )

    summary = resolve_current_run_vm_sync_state_relations(
        {str(endpoint.pk): "18"},
        run_id="run-stale-name-device",
    )

    state.refresh_from_db()
    assert state.proxmox_node_id == correct_node.pk
    assert summary.rows_changed == 0
    assert summary.unresolved == {
        "node_name_contradicts_native_device": {
            "count": 1,
            "sample_pks": [state.pk],
        }
    }


@pytest.mark.django_db
def test_current_run_relation_resolver_preserves_node_on_stale_name_without_device():
    endpoint, native_cluster, cluster = _owned_cluster("stale-name-no-device")
    correct_node = ProxmoxNode.objects.create(
        endpoint=endpoint,
        proxmox_cluster=cluster,
        name="stale-name-no-device-current",
        ip_address="2001:db8::87",
    )
    stale_node = ProxmoxNode.objects.create(
        endpoint=endpoint,
        proxmox_cluster=cluster,
        name="stale-name-no-device-old",
        ip_address="2001:db8::88",
    )
    state = _state(
        "stale-name-no-device-vm",
        19,
        last_run_id="run-stale-name-no-device",
        endpoint=endpoint,
        proxmox_node=correct_node,
        proxmox_node_name=stale_node.name,
        proxmox_cluster=cluster,
        proxmox_cluster_name=cluster.name,
        vm_cluster=native_cluster,
    )

    summary = resolve_current_run_vm_sync_state_relations(
        {str(endpoint.pk): "19"},
        run_id="run-stale-name-no-device",
    )

    state.refresh_from_db()
    assert state.proxmox_node_id == correct_node.pk
    assert summary.rows_changed == 0
    assert summary.unresolved == {
        "node_unverified_drift_without_native_device": {
            "count": 1,
            "sample_pks": [state.pk],
        }
    }


@pytest.mark.django_db
def test_current_run_relation_resolver_refuses_reused_backend_identity():
    mapped, mapped_native, mapped_tracking = _owned_cluster("reused-mapped")
    owner, owner_native, _owner_tracking = _owned_cluster("reused-owner")
    stale_node = ProxmoxNode.objects.create(
        endpoint=mapped,
        proxmox_cluster=mapped_tracking,
        name="reused-stale-node",
        ip_address="2001:db8::83",
    )
    state = _state(
        "reused-stamped-vm",
        16,
        last_run_id="run-reused-stamp",
        proxmox_node_name=stale_node.name,
        proxmox_cluster_name=mapped_tracking.name,
        vm_cluster=owner_native,
    )

    summary = resolve_current_run_vm_sync_state_relations(
        {str(mapped.pk): "16"},
        run_id="run-reused-stamp",
    )

    state.refresh_from_db()
    assert mapped.netbox_cluster_id == mapped_native.pk
    assert owner.netbox_cluster_id == owner_native.pk
    assert state.endpoint_id is None
    assert state.proxmox_node_id is None
    assert state.proxmox_cluster_id is None
    assert summary.rows_changed == 0
    assert summary.unresolved == {
        "native_cluster_ownership_ambiguous": {
            "count": 1,
            "sample_pks": [state.pk],
        }
    }


@pytest.mark.django_db
def test_current_run_relation_resolver_refuses_contradictory_node_cluster_graph():
    endpoint, native_cluster, linked_cluster = _owned_cluster("graph-refusal")
    other_cluster = ProxmoxCluster.objects.create(
        endpoint=endpoint,
        name="graph-refusal-other",
    )
    contradictory_node = ProxmoxNode.objects.create(
        endpoint=endpoint,
        proxmox_cluster=other_cluster,
        name="graph-refusal-node",
        ip_address="2001:db8::84",
    )
    state = _state(
        "graph-refusal-vm",
        17,
        last_run_id="run-graph-refusal",
        proxmox_node_name=contradictory_node.name,
        proxmox_cluster_name=linked_cluster.name,
        vm_cluster=native_cluster,
    )

    summary = resolve_current_run_vm_sync_state_relations(
        {str(endpoint.pk): "17"},
        run_id="run-graph-refusal",
    )

    state.refresh_from_db()
    assert state.endpoint_id == endpoint.pk
    assert state.proxmox_cluster_id == linked_cluster.pk
    assert state.proxmox_node_id is None
    assert summary.rows_changed == 1
    assert summary.unresolved == {
        "node_contradicts_cluster": {"count": 1, "sample_pks": [state.pk]}
    }
