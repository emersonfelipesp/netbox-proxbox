"""Real-Django migration contracts for InfluxDB token secret references."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import uuid

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOTS = (
    REPO_ROOT.parent / "netbox" / "netbox",
    REPO_ROOT.parents[1] / "nmulticloud-context" / "netbox" / "netbox",
)
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
except Exception as exc:  # pragma: no cover - external test harness availability
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is not available: {exc}",
        allow_module_level=True,
    )

from core.models import ObjectChange  # noqa: E402
from django.apps import apps as django_apps  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.contenttypes.models import ContentType  # noqa: E402
from django.db import IntegrityError, connection, transaction  # noqa: E402
from django.db.migrations.executor import MigrationExecutor  # noqa: E402
from django.test import Client, TestCase, TransactionTestCase  # noqa: E402
from django.urls import reverse  # noqa: E402

from netbox_proxbox.models import (  # noqa: E402
    ProxmoxCluster,
    ProxmoxEndpoint,
    ProxmoxMetricsInfluxDB,
)
from netbox_proxbox.models.proxmox_metrics import MASKED_SECRET_REF  # noqa: E402


VALID_SECRET_REF = "nms-secret:123e4567-e89b-12d3-a456-426614174000"
QUERY_CONSTRAINT = "netbox_proxbox_metrics_influxdb_query_token_is_ref"
WRITER_CONSTRAINT = "netbox_proxbox_metrics_influxdb_writer_token_is_ref"


class ProxmoxMetricsInfluxDBMigrationTest(TransactionTestCase):
    """Verify the current plugin leaf scrubs, quarantines, and constrains."""

    def _migrate_to(self, target: tuple[str, str]):
        executor = MigrationExecutor(connection)
        executor.migrate([target])
        executor = MigrationExecutor(connection)
        return executor.loader.project_state([target]).apps

    def _check_constraint_names(self, table_name: str) -> set[str]:
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, table_name)
        return {name for name, details in constraints.items() if details.get("check")}

    def _migration_edge(self) -> tuple[tuple[str, str], tuple[str, str]]:
        executor = MigrationExecutor(connection)
        leaves = tuple(executor.loader.graph.leaf_nodes("netbox_proxbox"))
        self.assertEqual(
            len(leaves),
            1,
            f"Expected exactly one netbox_proxbox migration leaf, found {leaves!r}",
        )
        leaf = leaves[0]
        in_app_dependencies = tuple(
            dependency
            for dependency in executor.loader.disk_migrations[leaf].dependencies
            if dependency[0] == "netbox_proxbox"
        )
        self.assertEqual(
            len(in_app_dependencies),
            1,
            f"Expected the metrics-security leaf to have one in-app parent, found "
            f"{in_app_dependencies!r}",
        )
        return in_app_dependencies[0], leaf

    def test_forward_scrubs_then_constrains_and_reverse_only_drops_constraints(
        self,
    ) -> None:
        migrate_from, migrate_to = self._migration_edge()
        try:
            apps_before = self._migrate_to(migrate_from)
            EndpointBefore = apps_before.get_model("netbox_proxbox", "ProxmoxEndpoint")
            ClusterBefore = apps_before.get_model("netbox_proxbox", "ProxmoxCluster")
            MetricsBefore = apps_before.get_model(
                "netbox_proxbox", "ProxmoxMetricsInfluxDB"
            )
            ContentTypeBefore = apps_before.get_model("contenttypes", "ContentType")
            ObjectChangeBefore = apps_before.get_model("core", "ObjectChange")
            endpoint = EndpointBefore.objects.create(name="metrics-migration-endpoint")
            cluster = ClusterBefore.objects.create(
                endpoint=endpoint,
                name="metrics-migration-cluster",
            )
            scrubbed = MetricsBefore.objects.create(
                name="scrubbed",
                endpoint=endpoint,
                proxmox_cluster=cluster,
                influx_url="raw-influx-url-must-be-scrubbed",
                query_token_secret_ref="plaintext-query-token",
                writer_token_secret_ref="nms-secret:partial",
                enabled=True,
                comments="Existing operator note.",
            )
            preserved = MetricsBefore.objects.create(
                name="preserved",
                endpoint=endpoint,
                proxmox_cluster=cluster,
                influx_url="https://influx.example.test:8086",
                query_token_secret_ref=VALID_SECRET_REF,
                writer_token_secret_ref="",
            )
            writer_only = MetricsBefore.objects.create(
                name="writer-only",
                endpoint=endpoint,
                proxmox_cluster=cluster,
                influx_url="https://writer-only.example.test:8086",
                query_token_secret_ref=VALID_SECRET_REF,
                writer_token_secret_ref="plaintext-optional-writer-token",
                enabled=True,
            )
            missing_query = MetricsBefore.objects.create(
                name="missing-query",
                endpoint=endpoint,
                proxmox_cluster=cluster,
                influx_url="https://missing-query.example.test:8086",
                query_token_secret_ref="",
                writer_token_secret_ref="",
                enabled=True,
            )
            metrics_content_type, _ = ContentTypeBefore.objects.get_or_create(
                app_label="netbox_proxbox",
                model="proxmoxmetricsinfluxdb",
            )
            historical_change = ObjectChangeBefore.objects.create(
                user_name="historical-auditor",
                request_id=uuid.uuid4(),
                action="update",
                changed_object_type=metrics_content_type,
                changed_object_id=scrubbed.pk,
                object_repr="historical metrics mapping",
                prechange_data={
                    "name": "before",
                    "influx_url": "https://user:secret@influx.example.test:8086",
                    "query_token_secret_ref": "historical-query-token",
                    "writer_token_secret_ref": "historical-writer-token",
                },
                postchange_data={
                    "name": "after",
                    "influx_url": "https://influx.example.test:8086",
                    "query_token_secret_ref": VALID_SECRET_REF,
                    "writer_token_secret_ref": "historical-writer-token-after",
                },
            )

            apps_after = self._migrate_to(migrate_to)
            MetricsAfter = apps_after.get_model(
                "netbox_proxbox", "ProxmoxMetricsInfluxDB"
            )
            ObjectChangeAfter = apps_after.get_model("core", "ObjectChange")
            scrubbed_after = MetricsAfter.objects.get(pk=scrubbed.pk)
            preserved_after = MetricsAfter.objects.get(pk=preserved.pk)
            writer_only_after = MetricsAfter.objects.get(pk=writer_only.pk)
            missing_query_after = MetricsAfter.objects.get(pk=missing_query.pk)
            historical_change_after = ObjectChangeAfter.objects.get(
                pk=historical_change.pk
            )

            self.assertEqual(scrubbed_after.query_token_secret_ref, "")
            self.assertEqual(scrubbed_after.writer_token_secret_ref, "")
            self.assertEqual(scrubbed_after.influx_url, "")
            self.assertFalse(scrubbed_after.enabled)
            self.assertIn("Existing operator note.", scrubbed_after.comments)
            self.assertIn("[Security quarantine]", scrubbed_after.comments)
            self.assertEqual(
                preserved_after.influx_url, "https://influx.example.test:8086"
            )
            self.assertEqual(preserved_after.query_token_secret_ref, VALID_SECRET_REF)
            self.assertEqual(preserved_after.writer_token_secret_ref, "")
            self.assertTrue(preserved_after.enabled)
            self.assertEqual(writer_only_after.writer_token_secret_ref, "")
            self.assertTrue(writer_only_after.enabled)
            self.assertEqual(missing_query_after.query_token_secret_ref, "")
            self.assertFalse(missing_query_after.enabled)
            self.assertIn("[Security quarantine]", missing_query_after.comments)
            self.assertEqual(
                historical_change_after.prechange_data["influx_url"], "********"
            )
            self.assertEqual(
                historical_change_after.prechange_data["query_token_secret_ref"],
                "********",
            )
            self.assertEqual(
                historical_change_after.prechange_data["writer_token_secret_ref"],
                "********",
            )
            self.assertEqual(
                historical_change_after.postchange_data["influx_url"],
                "https://influx.example.test:8086",
            )
            self.assertEqual(
                historical_change_after.postchange_data["query_token_secret_ref"],
                VALID_SECRET_REF,
            )
            self.assertEqual(
                historical_change_after.postchange_data["writer_token_secret_ref"],
                "********",
            )

            table_name = MetricsAfter._meta.db_table
            constraint_names = self._check_constraint_names(table_name)
            self.assertIn(QUERY_CONSTRAINT, constraint_names)
            self.assertIn(WRITER_CONSTRAINT, constraint_names)

            for field_name in (
                "query_token_secret_ref",
                "writer_token_secret_ref",
            ):
                with self.subTest(field=field_name):
                    with self.assertRaises(IntegrityError), transaction.atomic():
                        MetricsAfter.objects.filter(pk=preserved.pk).update(
                            **{field_name: "plaintext-token"}
                        )

            apps_reversed = self._migrate_to(migrate_from)
            MetricsReversed = apps_reversed.get_model(
                "netbox_proxbox", "ProxmoxMetricsInfluxDB"
            )
            ObjectChangeReversed = apps_reversed.get_model("core", "ObjectChange")
            still_scrubbed = MetricsReversed.objects.get(pk=scrubbed.pk)
            historical_change_reversed = ObjectChangeReversed.objects.get(
                pk=historical_change.pk
            )

            self.assertEqual(still_scrubbed.query_token_secret_ref, "")
            self.assertEqual(still_scrubbed.writer_token_secret_ref, "")
            self.assertEqual(still_scrubbed.influx_url, "")
            self.assertFalse(still_scrubbed.enabled)
            self.assertIn("[Security quarantine]", still_scrubbed.comments)
            self.assertEqual(
                historical_change_reversed.prechange_data["query_token_secret_ref"],
                "********",
            )
            reversed_constraints = self._check_constraint_names(table_name)
            self.assertNotIn(QUERY_CONSTRAINT, reversed_constraints)
            self.assertNotIn(WRITER_CONSTRAINT, reversed_constraints)

            MetricsReversed.objects.filter(pk=scrubbed.pk).update(
                query_token_secret_ref="accepted-only-after-reverse",
                writer_token_secret_ref="accepted-only-after-reverse",
            )
            unconstrained = MetricsReversed.objects.get(pk=scrubbed.pk)
            self.assertEqual(
                unconstrained.query_token_secret_ref, "accepted-only-after-reverse"
            )
            self.assertEqual(
                unconstrained.writer_token_secret_ref, "accepted-only-after-reverse"
            )
        finally:
            self._migrate_to(migrate_to)


class ProxmoxMetricsInfluxDBSecuritySurfaceTest(TestCase):
    """Exercise persisted bypasses and historical ObjectChange representations."""

    unsafe_url = "https://audit-user:audit-secret@influx.example.test:8086"
    unsafe_query_ref = "historical-query-token-must-not-render"
    unsafe_writer_ref = "historical-writer-token-must-not-render"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = get_user_model().objects.create_user(
            username="metrics-security-reviewer",
            is_staff=True,
            is_superuser=True,
        )
        cls.endpoint = ProxmoxEndpoint.objects.create(name="metrics-security-endpoint")
        cls.cluster = ProxmoxCluster.objects.create(
            endpoint=cls.endpoint,
            name="metrics-security-cluster",
        )
        cls.metrics = ProxmoxMetricsInfluxDB.objects.create(
            name="metrics-security-mapping",
            endpoint=cls.endpoint,
            proxmox_cluster=cls.cluster,
            influx_url="https://influx.example.test:8086",
            query_token_secret_ref=VALID_SECRET_REF,
        )

    def setUp(self) -> None:
        self.client = Client()
        self.client.force_login(self.user)

    def _sanitize_historical_snapshots(self) -> None:
        executor = MigrationExecutor(connection)
        leaves = tuple(executor.loader.graph.leaf_nodes("netbox_proxbox"))
        self.assertEqual(len(leaves), 1)
        migration_module = importlib.import_module(
            f"netbox_proxbox.migrations.{leaves[0][1]}"
        )
        migration_module._sanitize_objectchange_snapshots(
            django_apps,
            SimpleNamespace(connection=connection),
        )

    def _historical_change(self) -> ObjectChange:
        return ObjectChange.objects.create(
            user=self.user,
            request_id=uuid.uuid4(),
            action="update",
            changed_object_type=ContentType.objects.get_for_model(
                ProxmoxMetricsInfluxDB
            ),
            changed_object_id=self.metrics.pk,
            object_repr="historical metrics mapping",
            prechange_data={
                "name": "before",
                "influx_url": self.unsafe_url,
                "query_token_secret_ref": self.unsafe_query_ref,
                "writer_token_secret_ref": self.unsafe_writer_ref,
            },
            postchange_data={
                "name": "after",
                "influx_url": "https://influx.example.test:8086",
                "query_token_secret_ref": VALID_SECRET_REF,
                "writer_token_secret_ref": self.unsafe_writer_ref,
            },
        )

    def test_serialize_object_masks_values_before_new_changelog_snapshots(self) -> None:
        self.metrics.influx_url = self.unsafe_url
        self.metrics.query_token_secret_ref = self.unsafe_query_ref
        self.metrics.writer_token_secret_ref = self.unsafe_writer_ref

        serialized = self.metrics.serialize_object()
        self.metrics.snapshot()
        object_change = self.metrics.to_objectchange("update")

        self.assertEqual(serialized["influx_url"], MASKED_SECRET_REF)
        self.assertEqual(serialized["query_token_secret_ref"], MASKED_SECRET_REF)
        self.assertEqual(serialized["writer_token_secret_ref"], MASKED_SECRET_REF)
        for snapshot in (
            object_change.prechange_data,
            object_change.postchange_data,
        ):
            self.assertEqual(snapshot["influx_url"], MASKED_SECRET_REF)
            self.assertEqual(snapshot["query_token_secret_ref"], MASKED_SECRET_REF)
            self.assertEqual(snapshot["writer_token_secret_ref"], MASKED_SECRET_REF)

    def test_historical_changelog_page_and_rest_api_never_render_unsafe_values(
        self,
    ) -> None:
        # NetBox exposes ObjectChangeType only through a model's GraphQL
        # ``changelog`` field. This plugin does not register a GraphQL type for
        # ProxmoxMetricsInfluxDB, so there is no metrics changelog query to
        # exercise yet; the sanitized stored JSON is nevertheless the source a
        # future type would consume.
        historical_change = self._historical_change()
        self._sanitize_historical_snapshots()
        historical_change.refresh_from_db()

        changelog_response = self.client.get(historical_change.get_absolute_url())
        self.assertEqual(changelog_response.status_code, 200)
        for unsafe_value in (
            self.unsafe_url,
            self.unsafe_query_ref,
            self.unsafe_writer_ref,
        ):
            self.assertNotContains(changelog_response, unsafe_value)
        self.assertContains(changelog_response, MASKED_SECRET_REF)

        api_response = self.client.get(
            reverse("core-api:objectchange-detail", args=[historical_change.pk])
        )
        self.assertEqual(api_response.status_code, 200, api_response.content)
        payload = api_response.json()
        self.assertEqual(payload["prechange_data"]["influx_url"], MASKED_SECRET_REF)
        self.assertEqual(
            payload["prechange_data"]["query_token_secret_ref"], MASKED_SECRET_REF
        )
        self.assertEqual(
            payload["prechange_data"]["writer_token_secret_ref"], MASKED_SECRET_REF
        )
        self.assertEqual(
            payload["postchange_data"]["writer_token_secret_ref"], MASKED_SECRET_REF
        )

    def test_list_q_cannot_match_a_bypass_written_raw_url(self) -> None:
        oracle_marker = "raw-url-substring-oracle-marker"
        ProxmoxMetricsInfluxDB.objects.filter(pk=self.metrics.pk).update(
            influx_url=f"not-a-url-{oracle_marker}"
        )

        response = self.client.get(
            reverse("plugins:netbox_proxbox:proxmoxmetricsinfluxdb_list"),
            {"q": oracle_marker},
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotContains(response, self.metrics.name)
        self.assertNotContains(response, oracle_marker)

    def test_edit_get_hides_a_bypass_written_raw_url_and_warns(self) -> None:
        edit_marker = "raw-edit-url-must-not-render"
        ProxmoxMetricsInfluxDB.objects.filter(pk=self.metrics.pk).update(
            influx_url=edit_marker
        )

        response = self.client.get(
            reverse(
                "plugins:netbox_proxbox:proxmoxmetricsinfluxdb_edit",
                args=[self.metrics.pk],
            )
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotContains(response, edit_marker)
        self.assertContains(response, "A non-conforming stored URL was hidden.")
        self.assertEqual(response.context["form"]["influx_url"].value(), "")
