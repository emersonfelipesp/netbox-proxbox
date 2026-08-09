"""Real-Django coverage for unbounded Proxmox storage node membership."""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event, Lock
import time
from types import MethodType
from unittest.mock import patch

import pytest


pytestmark = pytest.mark.django_db


REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOT = REPO_ROOT.parent / "netbox" / "netbox"

for candidate in (REPO_ROOT, NETBOX_ROOT):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

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

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:  # pragma: no cover - depends on external test services
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is not available: {exc}", allow_module_level=True
    )

from django.contrib.auth import get_user_model  # noqa: E402
from django.db import connection, models  # noqa: E402
from django.db.migrations.executor import MigrationExecutor  # noqa: E402
from django.http import QueryDict  # noqa: E402
from django.test import SimpleTestCase, TestCase, TransactionTestCase  # noqa: E402
from django.urls import reverse  # noqa: E402
from users.models import Token  # noqa: E402
from virtualization.models import Cluster, ClusterType  # noqa: E402

from netbox_proxbox.api.serializers.storage import (  # noqa: E402
    ProxmoxStorageSerializer,
)
from netbox_proxbox.forms.storage import ProxmoxStorageForm  # noqa: E402
from netbox_proxbox.filtersets import ProxmoxStorageFilterSet  # noqa: E402
from netbox_proxbox.models import ProxmoxStorage  # noqa: E402
from netbox_proxbox.views import storage as storage_views  # noqa: E402
from netbox_proxbox.views.storage import ProxmoxStorageView  # noqa: E402


class ProxmoxStorageContentBudgetTest(SimpleTestCase):
    """Large memberships use bounded concurrency and explicit partial results."""

    @staticmethod
    def _content_call(view: ProxmoxStorageView, nodes: list[str]):
        return view._fetch_storage_content(
            nodes=nodes,
            storage_name="local",
            base_url="https://backend.example.test",
            auth_headers={"X-Proxbox-API-Key": "redacted-test-value"},
            verify_ssl=True,
            query_params={"proxmox_endpoint_ids": "11"},
        )

    def test_large_membership_never_exceeds_worker_bound(self) -> None:
        view = ProxmoxStorageView()
        nodes = [f"pve-{index:03d}" for index in range(view.max_content_nodes)]
        barrier = Barrier(view.content_request_workers)
        lock = Lock()
        active = 0
        maximum_active = 0

        def fake_fetch(self, **kwargs):
            nonlocal active, maximum_active
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            barrier.wait(timeout=2)
            with lock:
                active -= 1
            node = kwargs["route"].split("/")[3]
            return [{"volid": f"local:iso/{node}.iso"}], None

        view._fetch_backend_json = MethodType(fake_fetch, view)
        records, detail = self._content_call(view, nodes)

        self.assertIsNone(detail)
        self.assertEqual(len(records), len(nodes))
        self.assertEqual(maximum_active, view.content_request_workers)

    def test_deadline_returns_partial_result_without_serial_wait(self) -> None:
        view = ProxmoxStorageView()
        view.content_request_deadline = 0.02
        nodes = [f"pve-{index:03d}" for index in range(8)]
        release_slow_calls = Event()

        def fake_fetch(self, **kwargs):
            if "/pve-000/" in kwargs["route"]:
                return [{"volid": "local:iso/first.iso"}], None
            # Model a response that keeps producing bytes often enough that the
            # requests read timeout never fires. The view's absolute deadline,
            # not the socket inactivity timeout, must release the caller.
            release_slow_calls.wait(timeout=0.5)
            return [{"volid": "local:iso/late.iso"}], None

        view._fetch_backend_json = MethodType(fake_fetch, view)
        started = time.monotonic()
        records, detail = self._content_call(view, nodes)
        elapsed = time.monotonic() - started
        release_slow_calls.set()

        self.assertLess(elapsed, 0.5)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["volid"], "local:iso/first.iso")
        self.assertIsNotNone(detail)
        self.assertIn("1 of 8 node requests completed", detail)
        self.assertIn("0.02-second deadline", detail)

    def test_fast_membership_is_capped_before_request_amplification(self) -> None:
        view = ProxmoxStorageView()
        view.content_request_deadline = 1.0
        nodes = [f"pve-{index:03d}" for index in range(5000)]
        lock = Lock()
        started_calls = 0

        def fake_fetch(self, **kwargs):
            nonlocal started_calls
            with lock:
                started_calls += 1
            node = kwargs["route"].split("/")[3]
            return [{"volid": f"local:iso/{node}.iso"}], None

        view._fetch_backend_json = MethodType(fake_fetch, view)
        records, detail = self._content_call(view, nodes)
        with lock:
            call_count = started_calls

        self.assertEqual(call_count, view.max_content_nodes)
        self.assertEqual(len(records), view.max_content_nodes)
        self.assertIsNotNone(detail)
        self.assertIn(
            f"first {view.max_content_nodes} of 5000 nodes",
            detail,
        )

    def test_deadline_uses_non_blocking_executor_shutdown(self) -> None:
        view = ProxmoxStorageView()
        view.content_request_deadline = 0.02
        release_calls = Event()
        shutdown_calls: list[tuple[bool, bool]] = []

        class TrackingExecutor(ThreadPoolExecutor):
            def shutdown(
                self,
                wait: bool = True,
                *,
                cancel_futures: bool = False,
            ) -> None:
                shutdown_calls.append((wait, cancel_futures))
                super().shutdown(wait=wait, cancel_futures=cancel_futures)

        def fake_fetch(self, **kwargs):
            release_calls.wait(timeout=0.5)
            return [], None

        view._fetch_backend_json = MethodType(fake_fetch, view)
        with patch.object(storage_views, "ThreadPoolExecutor", TrackingExecutor):
            records, detail = self._content_call(
                view,
                [f"pve-{index:03d}" for index in range(80)],
            )
        release_calls.set()

        self.assertEqual(records, [])
        self.assertIsNotNone(detail)
        self.assertIn(
            f"0 of {view.max_content_nodes} node requests completed",
            detail,
        )
        self.assertEqual(shutdown_calls, [(False, True)])

    def test_real_malformed_records_never_count_as_a_successful_node(self) -> None:
        for payload in (
            {"detail": "backend failed"},
            [{"content": "iso", "size": 1024}],
            None,
        ):
            with self.subTest(payload=payload):
                view = ProxmoxStorageView()

                def fake_fetch(self, **kwargs):
                    return payload, None

                view._fetch_backend_json = MethodType(fake_fetch, view)
                records, detail = self._content_call(view, ["pve-000"])

                self.assertEqual(records, [])
                self.assertIsNotNone(detail)
                self.assertIn("0 of 1 node requests completed", detail)

    def test_late_refill_uses_remaining_timeout(self) -> None:
        view = ProxmoxStorageView()
        view.content_request_deadline = 0.05
        observed_timeouts: list[float] = []

        def fake_fetch(self, **kwargs):
            timeout = float(kwargs["request_timeout"])
            observed_timeouts.append(timeout)
            if timeout < 0.03:
                time.sleep(timeout)
                raise storage_views.requests.exceptions.Timeout("deadline")
            time.sleep(0.035)
            return [{"volid": f"local:iso/{kwargs['route'].split('/')[3]}.iso"}], None

        view._fetch_backend_json = MethodType(fake_fetch, view)
        started = time.monotonic()
        _records, detail = self._content_call(
            view,
            [f"pve-{index:03d}" for index in range(8)],
        )
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 0.2)
        self.assertIsNotNone(detail)
        self.assertGreaterEqual(len(observed_timeouts), view.content_request_workers)
        self.assertTrue(any(timeout < 0.03 for timeout in observed_timeouts))

    def test_partial_warning_is_outside_every_usage_data_branch(self) -> None:
        template = (
            REPO_ROOT
            / "netbox_proxbox"
            / "templates"
            / "netbox_proxbox"
            / "proxmoxstorage.html"
        ).read_text(encoding="utf-8")

        self.assertLess(
            template.index("{% if storage_content_detail %}"),
            template.index("{% if storage_usage %}"),
        )


class ProxmoxStorageNodesCapacityTest(TestCase):
    """Prove model, form, API, and persistence accept large node lists."""

    @classmethod
    def setUpTestData(cls) -> None:
        cluster_type = ClusterType.objects.create(
            name="storage-capacity-type",
            slug="storage-capacity-type",
        )
        cls.cluster = Cluster.objects.create(
            name="storage-capacity-cluster",
            type=cluster_type,
        )

    def test_nodes_is_unbounded_at_every_write_boundary(self) -> None:
        node_membership = ",".join(f"pve-{index:03d}" for index in range(80))
        self.assertGreater(len(node_membership), 255)

        model_field = ProxmoxStorage._meta.get_field("nodes")
        self.assertIsInstance(model_field, models.TextField)
        self.assertEqual(model_field.clean(node_membership, None), node_membership)
        self.assertEqual(
            ProxmoxStorageForm().fields["nodes"].clean(node_membership),
            node_membership,
        )
        self.assertEqual(
            ProxmoxStorageSerializer().fields["nodes"].run_validation(node_membership),
            node_membership,
        )

        storage = ProxmoxStorage.objects.create(
            cluster=self.cluster,
            name="long-node-membership",
            nodes=node_membership,
        )
        storage.refresh_from_db()
        self.assertEqual(storage.nodes, node_membership)

    def test_nodes_filter_accepts_multiple_exact_memberships(self) -> None:
        memberships = [
            ",".join(f"pve-a-{index:03d}" for index in range(80)),
            ",".join(f"pve-b-{index:03d}" for index in range(80)),
        ]
        for index, membership in enumerate(memberships):
            ProxmoxStorage.objects.create(
                cluster=self.cluster,
                name=f"multi-value-storage-{index}",
                nodes=membership,
            )
        ProxmoxStorage.objects.create(
            cluster=self.cluster,
            name="multi-value-storage-other",
            nodes="pve-other",
        )
        query = QueryDict(mutable=True)
        query.setlist("nodes", memberships)

        filtered = ProxmoxStorageFilterSet(
            data=query,
            queryset=ProxmoxStorage.objects.all(),
        )

        self.assertTrue(filtered.is_valid(), filtered.errors)
        self.assertCountEqual(
            filtered.qs.values_list("nodes", flat=True),
            memberships,
        )

    def test_rest_list_and_bulk_update_preserve_long_memberships(self) -> None:
        storages = [
            ProxmoxStorage.objects.create(
                cluster=self.cluster,
                name=f"api-long-membership-{index}",
                nodes="pve-before",
            )
            for index in range(2)
        ]
        memberships = [
            ",".join(f"pve-api-{index}-{node:03d}" for node in range(80))
            for index in range(2)
        ]
        user = get_user_model().objects.create_user(
            username="storage-long-membership-api",
            is_staff=True,
            is_superuser=True,
        )
        token = Token.objects.create(user=user)
        headers = {"HTTP_AUTHORIZATION": f"Token {token.key}"}
        list_url = reverse("plugins-api:netbox_proxbox-api:storage-list")

        bulk_response = self.client.patch(
            list_url,
            data=json.dumps(
                [
                    {"id": storage.pk, "nodes": membership}
                    for storage, membership in zip(storages, memberships, strict=True)
                ]
            ),
            content_type="application/json",
            **headers,
        )

        self.assertEqual(bulk_response.status_code, 200, bulk_response.content)
        self.assertCountEqual(
            [row["nodes"] for row in bulk_response.json()],
            memberships,
        )
        list_response = self.client.get(
            list_url,
            data={"nodes": memberships},
            **headers,
        )
        self.assertEqual(list_response.status_code, 200, list_response.content)
        self.assertCountEqual(
            [row["nodes"] for row in list_response.json()["results"]],
            memberships,
        )


class ProxmoxStorageNodesCapacityMigrationTest(TransactionTestCase):
    """Prove the current leaf's expand-only rollback/reapply behavior."""

    def _migrate_to(self, target: tuple[str, str]):
        executor = MigrationExecutor(connection)
        executor.migrate([target])
        executor = MigrationExecutor(connection)
        return executor.loader.project_state([target]).apps

    def _migration_edge(self) -> tuple[tuple[str, str], tuple[str, str]]:
        executor = MigrationExecutor(connection)
        leaf_targets = executor.loader.graph.leaf_nodes("netbox_proxbox")
        self.assertEqual(
            len(leaf_targets),
            1,
            f"Expected exactly one netbox_proxbox migration leaf: {leaf_targets}",
        )
        migrate_to = leaf_targets[0]
        self.assertTrue(
            migrate_to[1].endswith("_storage_nodes_text"),
            f"Current plugin leaf is not the storage nodes migration: {migrate_to}",
        )
        migration = executor.loader.get_migration(*migrate_to)
        plugin_dependencies = [
            dependency
            for dependency in migration.dependencies
            if dependency[0] == "netbox_proxbox"
        ]
        self.assertEqual(
            len(plugin_dependencies),
            1,
            f"Expected one plugin parent for {migrate_to}: {plugin_dependencies}",
        )
        return plugin_dependencies[0], migrate_to

    def test_forward_rollback_and_reapply_preserve_large_membership(self) -> None:
        migrate_from, migrate_to = self._migration_edge()
        original_membership = ",".join(f"pve-{index:03d}" for index in range(20))
        large_membership = ",".join(f"pve-{index:03d}" for index in range(80))
        rollback_membership = f"{large_membership},pve-rollback"
        self.assertLessEqual(len(original_membership), 255)
        self.assertGreater(len(large_membership), 255)

        try:
            apps_before = self._migrate_to(migrate_from)
            ClusterTypeBefore = apps_before.get_model("virtualization", "ClusterType")
            ClusterBefore = apps_before.get_model("virtualization", "Cluster")
            StorageBefore = apps_before.get_model("netbox_proxbox", "ProxmoxStorage")
            cluster_type = ClusterTypeBefore.objects.create(
                name="storage-migration-type",
                slug="storage-migration-type",
            )
            cluster = ClusterBefore.objects.create(
                name="storage-migration-cluster",
                type=cluster_type,
            )
            storage = StorageBefore.objects.create(
                cluster=cluster,
                name="storage-migration-membership",
                nodes=original_membership,
            )

            apps_after = self._migrate_to(migrate_to)
            StorageAfter = apps_after.get_model("netbox_proxbox", "ProxmoxStorage")
            migrated = StorageAfter.objects.get(pk=storage.pk)
            self.assertEqual(migrated.nodes, original_membership)
            migrated.nodes = large_membership
            migrated.save(update_fields=("nodes",))

            apps_rollback = self._migrate_to(migrate_from)
            StorageRollback = apps_rollback.get_model(
                "netbox_proxbox", "ProxmoxStorage"
            )
            rolled_back = StorageRollback.objects.get(pk=storage.pk)
            self.assertEqual(rolled_back.nodes, large_membership)
            StorageRollback.objects.filter(pk=storage.pk).update(
                nodes=rollback_membership
            )

            apps_reapplied = self._migrate_to(migrate_to)
            StorageReapplied = apps_reapplied.get_model(
                "netbox_proxbox", "ProxmoxStorage"
            )
            self.assertEqual(
                StorageReapplied.objects.get(pk=storage.pk).nodes,
                rollback_membership,
            )
        finally:
            self._migrate_to(migrate_to)
