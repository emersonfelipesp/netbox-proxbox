"""Real-NetBox recovery of cross-endpoint cluster tracking links left by old releases."""
# ruff: noqa: E402

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest

from tests.netbox_test_paths import netbox_source_roots


REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOTS = netbox_source_roots(REPO_ROOT)
_REQUIRE_DJANGO = os.environ.get("NETBOX_PROXBOX_REQUIRE_DJANGO", "").lower() in (
    "1",
    "true",
    "yes",
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
    if _REQUIRE_DJANGO:
        raise RuntimeError("A real Django package is required for this test module.")
    pytest.skip(
        "The mocked suite does not provide a real Django package.",
        allow_module_level=True,
    )

for candidate_path in NETBOX_ROOTS:
    candidate_string = str(candidate_path)
    if candidate_path.exists() and candidate_string not in sys.path:
        sys.path.insert(0, candidate_string)

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:  # pragma: no cover - external harness availability
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is not available: {exc}", allow_module_level=True
    )


from unittest.mock import patch  # noqa: E402

from django.core.exceptions import ValidationError  # noqa: E402
from django.test import TestCase, TransactionTestCase  # noqa: E402
from virtualization.models import Cluster, ClusterType  # noqa: E402

from netbox_proxbox.models import (  # noqa: E402
    ProxboxClusterSyncState,
    ProxboxPluginSettings,
    ProxmoxCluster,
    ProxmoxEndpoint,
)
from netbox_proxbox.schemas import ProxmoxClusterStatusResponse  # noqa: E402
from netbox_proxbox.services import sync_cluster  # noqa: E402
from netbox_proxbox.services.cluster_binding import (  # noqa: E402
    ClusterBindingConflict,
    synchronize_cluster,
)
from netbox_proxbox.services.cluster_tracking_repair import (  # noqa: E402
    TrackingLink,
    discovery_target_identity,
    plan_foreign_link_release,
    release_foreign_tracking_links,
)
from tests.django_support import make_user  # noqa: E402

NAMES = ("pve-alpha", "pve-bravo", "pve-charlie")


def _status(name: str) -> ProxmoxClusterStatusResponse:
    return ProxmoxClusterStatusResponse.model_validate(
        [
            {"type": "cluster", "name": name, "id": f"cluster/{name}", "nodes": 1},
            {
                "type": "node",
                "name": f"{name}-node1",
                "nodeid": 1,
                "online": 1,
                "ip": "127.0.0.1",
            },
        ]
    )


class _CrossLinkedFixture:
    """Reproduce the state old unscoped discovery plus name-based linking left."""

    def setUp(self) -> None:
        ProxboxPluginSettings.objects.get_or_create(singleton_key="default")
        self.admin = make_user("repair-admin", is_superuser=True)
        self.cluster_type = ClusterType.objects.create(name="PVE", slug="pve")
        self.endpoints = [
            ProxmoxEndpoint.objects.create(
                name=f"Endpoint {index}",
                domain=f"endpoint{index}.example.test",
                enabled=True,
            )
            for index in range(3)
        ]
        self.cores = [
            Cluster.objects.create(name=name, type=self.cluster_type) for name in NAMES
        ]
        # Every endpoint holds a tracking row for every cluster, each linked by
        # name to the native cluster. Bulk creation bypasses today's validation,
        # exactly as the historical writers did.
        ProxmoxCluster.objects.bulk_create(
            [
                ProxmoxCluster(endpoint=endpoint, name=name, netbox_cluster=core)
                for endpoint in self.endpoints
                for name, core in zip(NAMES, self.cores)
            ]
        )
        # Each native cluster's sidecar points at a *foreign* endpoint's row.
        for index, core in enumerate(self.cores):
            foreign = self.endpoints[(index + 1) % 3]
            row = ProxmoxCluster.objects.get(endpoint=foreign, netbox_cluster=core)
            ProxboxClusterSyncState.objects.bulk_create(
                [
                    ProxboxClusterSyncState(
                        cluster=core, proxmox_cluster=row, proxmox_cluster_name=row.name
                    )
                ]
            )
        self.values = {"mode": "cluster", "cluster_type": self.cluster_type}

    def _claim(self, index: int):
        return synchronize_cluster(
            self.endpoints[index].pk, self.admin, self.values | {"name": NAMES[index]}
        )

    def _cluster_sync(self, index: int, status=None):
        endpoint = self.endpoints[index]
        with (
            patch.object(
                sync_cluster, "resolve_backend_endpoint_id", return_value=(7, None)
            ),
            patch.object(
                sync_cluster,
                "_fetch_cluster_and_node_data",
                return_value=(status or _status(NAMES[index]), []),
            ),
        ):
            return sync_cluster.sync_cluster_and_nodes(
                endpoint.pk, fastapi_url="https://backend.example.test", auth_headers={}
            )

    def _release(self, index: int, name: str) -> int:
        endpoint = ProxmoxEndpoint.objects.get(pk=self.endpoints[index].pk)
        return release_foreign_tracking_links(
            endpoint.pk, name, discovery_target_identity(endpoint)
        )

    def _linked_snapshot(self) -> tuple[list, list]:
        links = list(
            ProxmoxCluster.objects.order_by("pk").values_list("pk", "netbox_cluster_id")
        )
        sidecars = list(
            ProxboxClusterSyncState.objects.order_by("pk").values_list(
                "pk", "proxmox_cluster_id"
            )
        )
        return links, sidecars


class CrossLinkedTrackingRecoveryTest(_CrossLinkedFixture, TestCase):
    def test_standalone_sync_stores_local_node_cluster_uid(self) -> None:
        endpoint = ProxmoxEndpoint.objects.create(
            name="standalone-uid-endpoint",
            domain="standalone-uid.example.test",
            enabled=True,
        )
        status = ProxmoxClusterStatusResponse.model_validate(
            [
                {
                    "type": "node",
                    "name": "standalone-uid-node",
                    "id": "node/standalone-uid-node",
                    "local": 1,
                    "online": 1,
                    "cluster-id": "standalone-cluster-uid",
                }
            ]
        )
        with (
            patch.object(
                sync_cluster, "resolve_backend_endpoint_id", return_value=(7, None)
            ),
            patch.object(
                sync_cluster,
                "_fetch_cluster_and_node_data",
                return_value=(status, []),
            ),
        ):
            result = sync_cluster.sync_cluster_and_nodes(
                endpoint.pk,
                fastapi_url="https://backend.example.test",
                auth_headers={},
            )
        self.assertTrue(result.success, result.error)
        tracking = ProxmoxCluster.objects.get(
            endpoint=endpoint, name="standalone-uid-node"
        )
        self.assertEqual(tracking.proxmox_cluster_uid, "standalone-cluster-uid")

    def test_poisoned_state_reproduces_both_reported_failures(self) -> None:
        row = ProxmoxCluster.objects.get(endpoint=self.endpoints[0], name=NAMES[0])
        row.quorate = True
        with self.assertRaisesMessage(
            ValidationError, "Resolve this endpoint's conflicting tracking links first."
        ):
            row.save()
        for index in range(3):
            with self.assertRaises(ClusterBindingConflict):
                self._claim(index)

    def test_one_job_pass_releases_foreign_links_and_every_claim_succeeds(
        self,
    ) -> None:
        results = [self._cluster_sync(index) for index in range(3)]
        self.assertEqual([r.tracking_links_released for r in results], [2, 2, 2])
        # The last endpoint has no remaining foreign claim on its cluster.
        self.assertTrue(results[2].success, results[2].error)
        for index, endpoint in enumerate(self.endpoints):
            linked = ProxmoxCluster.objects.filter(
                endpoint=endpoint, netbox_cluster__isnull=False
            )
            self.assertEqual(
                list(linked.values_list("name", "netbox_cluster_id")),
                [(NAMES[index], self.cores[index].pk)],
            )
            # Rows are kept, only their foreign link is cleared.
            self.assertEqual(
                ProxmoxCluster.objects.filter(endpoint=endpoint).count(), 3
            )
        # The devices stage claim now succeeds for every endpoint in the same run.
        for index in range(3):
            core, tracking, created = self._claim(index)
            self.assertFalse(created)
            self.assertEqual(core.pk, self.cores[index].pk)
            self.assertEqual(tracking.endpoint_id, self.endpoints[index].pk)
            self.assertEqual(
                ProxboxClusterSyncState.objects.get(cluster=core).proxmox_cluster_id,
                tracking.pk,
            )
            self.endpoints[index].refresh_from_db()
            self.assertEqual(self.endpoints[index].netbox_cluster_id, core.pk)
        # A second job pass is clean for every endpoint.
        again = [self._cluster_sync(index) for index in range(3)]
        self.assertTrue(all(r.success for r in again), [r.error for r in again])
        self.assertEqual([r.tracking_links_released for r in again], [0, 0, 0])
        self.assertEqual(Cluster.objects.count(), 3)

    def test_no_live_name_match_releases_nothing(self) -> None:
        released = self._release(0, "unknown")
        self.assertEqual(released, 0)
        self.assertEqual(
            ProxmoxCluster.objects.filter(
                endpoint=self.endpoints[0], netbox_cluster__isnull=False
            ).count(),
            3,
        )

    def test_unnamed_cluster_record_never_uses_the_endpoint_name(self) -> None:
        # The editable endpoint name matches a *foreign* cluster's row; it must
        # never become release evidence when discovery reports no name.
        ProxmoxEndpoint.objects.filter(pk=self.endpoints[0].pk).update(name=NAMES[1])
        self.endpoints[0].refresh_from_db()
        before = self._linked_snapshot()
        status = ProxmoxClusterStatusResponse.model_validate(
            [{"type": "cluster", "name": None, "nodes": 1}]
        )
        result = self._cluster_sync(0, status)
        self.assertEqual(result.tracking_links_released, 0)
        self.assertEqual(self._linked_snapshot(), before)

    def test_multiple_cluster_records_release_nothing_in_any_order(self) -> None:
        before = self._linked_snapshot()
        for names in (NAMES[:2], NAMES[:2][::-1]):
            status = ProxmoxClusterStatusResponse.model_validate(
                [{"type": "cluster", "name": name, "nodes": 1} for name in names]
            )
            result = self._cluster_sync(0, status)
            self.assertEqual(result.tracking_links_released, 0)
            self.assertEqual(self._linked_snapshot(), before)

    def test_target_edited_during_discovery_releases_nothing(self) -> None:
        before = self._linked_snapshot()
        endpoint = self.endpoints[0]

        def retarget_then_answer(*_args, **_kwargs):
            # The operator points the endpoint at another Proxmox target while
            # the old target's discovery request is still in flight.
            ProxmoxEndpoint.objects.filter(pk=endpoint.pk).update(
                domain="retargeted.example.test"
            )
            return _status(NAMES[0]), []

        with (
            patch.object(
                sync_cluster, "resolve_backend_endpoint_id", return_value=(7, None)
            ),
            patch.object(
                sync_cluster,
                "_fetch_cluster_and_node_data",
                side_effect=retarget_then_answer,
            ),
        ):
            result = sync_cluster.sync_cluster_and_nodes(
                endpoint.pk, fastapi_url="https://backend.example.test", auth_headers={}
            )
        self.assertEqual(result.tracking_links_released, 0)
        self.assertEqual(self._linked_snapshot(), before)
        # An empty or different captured target is refused outright.
        self.assertEqual(release_foreign_tracking_links(endpoint.pk, NAMES[0], ""), 0)
        self.assertEqual(self._linked_snapshot(), before)

    def test_conflicting_authority_releases_nothing(self) -> None:
        ProxmoxEndpoint.objects.filter(pk=self.endpoints[0].pk).update(
            netbox_cluster=self.cores[1]
        )
        self.assertEqual(self._release(0, NAMES[0]), 0)

    def test_disabled_endpoint_and_disabled_cluster_mode_release_nothing(self) -> None:
        ProxmoxEndpoint.objects.filter(pk=self.endpoints[0].pk).update(enabled=False)
        self.assertEqual(self._release(0, NAMES[0]), 0)
        ProxmoxEndpoint.objects.filter(pk=self.endpoints[0].pk).update(enabled=True)
        with patch.object(sync_cluster, "_endpoint_sync_mode", return_value="disabled"):
            result = self._cluster_sync(0)
        self.assertEqual(result.tracking_links_released, 0)
        self.assertEqual(
            ProxmoxCluster.objects.filter(
                endpoint=self.endpoints[0], netbox_cluster__isnull=False
            ).count(),
            3,
        )

    def test_release_never_writes_other_endpoints_or_native_clusters(self) -> None:
        before = {
            row.pk: row.netbox_cluster_id
            for row in ProxmoxCluster.objects.exclude(endpoint=self.endpoints[0])
        }
        names = {core.pk: core.name for core in self.cores}
        self.assertEqual(self._release(0, NAMES[0]), 2)
        after = {
            row.pk: row.netbox_cluster_id
            for row in ProxmoxCluster.objects.exclude(endpoint=self.endpoints[0])
        }
        self.assertEqual(before, after)
        self.assertEqual({core.pk: core.name for core in Cluster.objects.all()}, names)
        # Only the sidecar that pointed at a released row of this endpoint lost
        # its pointer; the cluster 2 sidecar points at endpoint 0's row for it.
        sidecar = ProxboxClusterSyncState.objects.get(cluster=self.cores[2])
        self.assertIsNone(sidecar.proxmox_cluster_id)
        untouched = ProxboxClusterSyncState.objects.get(cluster=self.cores[0])
        self.assertIsNotNone(untouched.proxmox_cluster_id)


class CrossLinkedTrackingRecoveryCommitTest(_CrossLinkedFixture, TransactionTestCase):
    """Prove the release commits even when the following persist fails."""

    def test_release_commits_independently_of_the_failed_persist(self) -> None:
        result = self._cluster_sync(0)
        self.assertFalse(result.success)
        self.assertIn("Another endpoint's tracking row claims", result.error)
        self.assertEqual(result.tracking_links_released, 2)
        # Autocommit: a fresh read sees the committed release despite the
        # rolled-back persist transaction that followed it.
        self.assertEqual(
            list(
                ProxmoxCluster.objects.filter(
                    endpoint=self.endpoints[0], netbox_cluster__isnull=False
                ).values_list("name", flat=True)
            ),
            [NAMES[0]],
        )
        for index in (1, 2):
            self.assertTrue(self._cluster_sync(index).tracking_links_released)
        for index in range(3):
            core, _, _ = self._claim(index)
            self.assertEqual(core.pk, self.cores[index].pk)


class ReleasePlanTest(TestCase):
    def test_plan_rules(self) -> None:
        a, b, c = (
            TrackingLink(1, "a", 10),
            TrackingLink(2, "b", 20),
            TrackingLink(3, "c", 30),
        )
        self.assertEqual(plan_foreign_link_release([a, b, c], "a", None), [b, c])
        self.assertEqual(plan_foreign_link_release([a, b, c], "a", 10), [b, c])
        self.assertEqual(plan_foreign_link_release([a, b, c], "a", 20), [])
        self.assertEqual(plan_foreign_link_release([a, b, c], "zzz", None), [])
        self.assertEqual(plan_foreign_link_release([a, b, c], "", None), [])
        # A single link (for example a renamed cluster) is never released.
        self.assertEqual(plan_foreign_link_release([a], "renamed", None), [])
        # Duplicate links to the kept cluster stay for operator review.
        dup = TrackingLink(4, "a-old", 10)
        self.assertEqual(plan_foreign_link_release([a, dup, b], "a", None), [b])
