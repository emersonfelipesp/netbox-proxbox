"""Real-Django coverage for unbounded Proxmox storage node membership."""

from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event, Lock
import time
from types import MethodType
from unittest.mock import patch

import pytest


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

from django.db import connection, models  # noqa: E402
from django.db.migrations.executor import MigrationExecutor  # noqa: E402
from django.test import SimpleTestCase, TestCase, TransactionTestCase  # noqa: E402
from virtualization.models import Cluster, ClusterType  # noqa: E402

from netbox_proxbox.api.serializers.storage import (  # noqa: E402
    ProxmoxStorageSerializer,
)
from netbox_proxbox.forms.storage import ProxmoxStorageForm  # noqa: E402
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
        nodes = [f"pve-{index:03d}" for index in range(80)]
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
        nodes = [f"pve-{index:03d}" for index in range(80)]
        release_slow_calls = Event()

        def fake_fetch(self, **kwargs):
            if "/pve-000/" in kwargs["route"]:
                return [{"volid": "local:iso/first.iso"}], None
            release_slow_calls.wait(timeout=kwargs["request_timeout"])
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
        self.assertIn("1 of 80 node requests completed", detail)
        self.assertIn("0.02-second deadline", detail)

    def test_deadline_never_queues_more_than_the_worker_window(self) -> None:
        view = ProxmoxStorageView()
        view.content_request_deadline = 0.02
        nodes = [f"pve-{index:03d}" for index in range(5000)]
        release_calls = Event()
        lock = Lock()
        started_calls = 0

        def fake_fetch(self, **kwargs):
            nonlocal started_calls
            with lock:
                started_calls += 1
            release_calls.wait(timeout=kwargs["request_timeout"])
            return [], None

        view._fetch_backend_json = MethodType(fake_fetch, view)
        started = time.monotonic()
        records, detail = self._content_call(view, nodes)
        elapsed = time.monotonic() - started
        with lock:
            calls_before_release = started_calls
        release_calls.set()

        self.assertLess(elapsed, 0.5)
        self.assertEqual(records, [])
        self.assertIsNotNone(detail)
        self.assertEqual(calls_before_release, view.content_request_workers)

    def test_malformed_result_is_partial_and_still_cleans_up_workers(self) -> None:
        view = ProxmoxStorageView()
        view.content_request_deadline = 0.02
        release_calls = Event()
        shutdown_calls: list[tuple[bool, bool, bool]] = []

        class TrackingExecutor(ThreadPoolExecutor):
            def shutdown(
                self,
                wait: bool = True,
                *,
                cancel_futures: bool = False,
            ) -> None:
                super().shutdown(wait=wait, cancel_futures=cancel_futures)
                shutdown_calls.append(
                    (
                        wait,
                        cancel_futures,
                        any(thread.is_alive() for thread in self._threads),
                    )
                )

        def fake_fetch(self, **kwargs):
            if "/pve-000/" in kwargs["route"]:
                return {"detail": "backend failed"}, None
            release_calls.wait(timeout=kwargs["request_timeout"])
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
        self.assertIn("0 of 80 node requests completed", detail)
        self.assertEqual(shutdown_calls, [(True, True, False)])

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

    def test_late_refill_uses_remaining_timeout_and_leaves_no_threads(self) -> None:
        view = ProxmoxStorageView()
        view.content_request_deadline = 0.05
        observed_timeouts: list[float] = []
        shutdown_threads_alive: list[bool] = []

        class TrackingExecutor(ThreadPoolExecutor):
            def shutdown(
                self,
                wait: bool = True,
                *,
                cancel_futures: bool = False,
            ) -> None:
                super().shutdown(wait=wait, cancel_futures=cancel_futures)
                shutdown_threads_alive.append(
                    any(thread.is_alive() for thread in self._threads)
                )

        def fake_fetch(self, **kwargs):
            timeout = float(kwargs["request_timeout"])
            observed_timeouts.append(timeout)
            if timeout < 0.03:
                time.sleep(timeout)
                raise storage_views.requests.exceptions.Timeout("deadline")
            time.sleep(0.035)
            return [{"volid": f"local:iso/{kwargs['route'].split('/')[3]}.iso"}], None

        view._fetch_backend_json = MethodType(fake_fetch, view)
        with patch.object(storage_views, "ThreadPoolExecutor", TrackingExecutor):
            started = time.monotonic()
            _records, detail = self._content_call(
                view,
                [f"pve-{index:03d}" for index in range(8)],
            )
            elapsed = time.monotonic() - started

        self.assertLess(elapsed, 0.2)
        self.assertIsNotNone(detail)
        self.assertEqual(shutdown_threads_alive, [False])
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


class ProxmoxStorageNodesCapacityMigrationTest(TransactionTestCase):
    """Prove forward preservation and expand-only rollback/reapply behavior."""

    migrate_from = ("netbox_proxbox", "0078_sync_state_last_synced_role")
    migrate_to = ("netbox_proxbox", "0079_storage_nodes_text")

    def _migrate_to(self, target: tuple[str, str]):
        executor = MigrationExecutor(connection)
        executor.migrate([target])
        executor = MigrationExecutor(connection)
        return executor.loader.project_state([target]).apps

    def test_forward_rollback_and_reapply_preserve_large_membership(self) -> None:
        original_membership = ",".join(f"pve-{index:03d}" for index in range(20))
        large_membership = ",".join(f"pve-{index:03d}" for index in range(80))
        rollback_membership = f"{large_membership},pve-rollback"
        self.assertLessEqual(len(original_membership), 255)
        self.assertGreater(len(large_membership), 255)

        try:
            apps_0078 = self._migrate_to(self.migrate_from)
            ClusterType0078 = apps_0078.get_model("virtualization", "ClusterType")
            Cluster0078 = apps_0078.get_model("virtualization", "Cluster")
            Storage0078 = apps_0078.get_model("netbox_proxbox", "ProxmoxStorage")
            cluster_type = ClusterType0078.objects.create(
                name="storage-migration-type",
                slug="storage-migration-type",
            )
            cluster = Cluster0078.objects.create(
                name="storage-migration-cluster",
                type=cluster_type,
            )
            storage = Storage0078.objects.create(
                cluster=cluster,
                name="storage-migration-membership",
                nodes=original_membership,
            )

            apps_0079 = self._migrate_to(self.migrate_to)
            Storage0079 = apps_0079.get_model("netbox_proxbox", "ProxmoxStorage")
            migrated = Storage0079.objects.get(pk=storage.pk)
            self.assertEqual(migrated.nodes, original_membership)
            migrated.nodes = large_membership
            migrated.save(update_fields=("nodes",))

            apps_rollback = self._migrate_to(self.migrate_from)
            StorageRollback = apps_rollback.get_model(
                "netbox_proxbox", "ProxmoxStorage"
            )
            rolled_back = StorageRollback.objects.get(pk=storage.pk)
            self.assertEqual(rolled_back.nodes, large_membership)
            StorageRollback.objects.filter(pk=storage.pk).update(
                nodes=rollback_membership
            )

            apps_reapplied = self._migrate_to(self.migrate_to)
            StorageReapplied = apps_reapplied.get_model(
                "netbox_proxbox", "ProxmoxStorage"
            )
            self.assertEqual(
                StorageReapplied.objects.get(pk=storage.pk).nodes,
                rollback_membership,
            )
        finally:
            self._migrate_to(self.migrate_to)
