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

from virtualization.models import VirtualMachine  # noqa: E402

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


def _state(name: str, raw_id: int, **relations) -> ProxboxVirtualMachineSyncState:
    vm = VirtualMachine.objects.create(name=name, status="active")
    return ProxboxVirtualMachineSyncState.objects.create(
        virtual_machine=vm,
        proxmox_endpoint_raw_id=raw_id,
        **relations,
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
