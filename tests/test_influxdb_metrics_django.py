"""Real-Django migration contracts for InfluxDB token secret references."""

from __future__ import annotations

import os
from pathlib import Path
import sys

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

from django.db import IntegrityError, connection, transaction  # noqa: E402
from django.db.migrations.executor import MigrationExecutor  # noqa: E402
from django.test import TransactionTestCase  # noqa: E402


VALID_SECRET_REF = "nms-secret:123e4567-e89b-12d3-a456-426614174000"
QUERY_CONSTRAINT = "netbox_proxbox_metrics_influxdb_query_token_is_ref"
WRITER_CONSTRAINT = "netbox_proxbox_metrics_influxdb_writer_token_is_ref"


class ProxmoxMetricsInfluxDBMigrationTest(TransactionTestCase):
    """Verify migration 0079 scrubs once and constrains both token columns."""

    migrate_from = ("netbox_proxbox", "0078_sync_state_last_synced_role")
    migrate_to = (
        "netbox_proxbox",
        "0079_metrics_influxdb_secret_ref_constraints",
    )

    def _migrate_to(self, target: tuple[str, str]):
        executor = MigrationExecutor(connection)
        executor.migrate([target])
        executor = MigrationExecutor(connection)
        return executor.loader.project_state([target]).apps

    def _check_constraint_names(self, table_name: str) -> set[str]:
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, table_name)
        return {name for name, details in constraints.items() if details.get("check")}

    def test_forward_scrubs_then_constrains_and_reverse_only_drops_constraints(
        self,
    ) -> None:
        try:
            apps_0078 = self._migrate_to(self.migrate_from)
            Endpoint0078 = apps_0078.get_model("netbox_proxbox", "ProxmoxEndpoint")
            Cluster0078 = apps_0078.get_model("netbox_proxbox", "ProxmoxCluster")
            Metrics0078 = apps_0078.get_model(
                "netbox_proxbox", "ProxmoxMetricsInfluxDB"
            )
            endpoint = Endpoint0078.objects.create(name="metrics-migration-endpoint")
            cluster = Cluster0078.objects.create(
                endpoint=endpoint,
                name="metrics-migration-cluster",
            )
            scrubbed = Metrics0078.objects.create(
                name="scrubbed",
                endpoint=endpoint,
                proxmox_cluster=cluster,
                influx_url="https://influx.example.test:8086",
                query_token_secret_ref="plaintext-query-token",
                writer_token_secret_ref="nms-secret:partial",
            )
            preserved = Metrics0078.objects.create(
                name="preserved",
                endpoint=endpoint,
                proxmox_cluster=cluster,
                influx_url="https://influx.example.test:8086",
                query_token_secret_ref=VALID_SECRET_REF,
                writer_token_secret_ref="",
            )

            apps_0079 = self._migrate_to(self.migrate_to)
            Metrics0079 = apps_0079.get_model(
                "netbox_proxbox", "ProxmoxMetricsInfluxDB"
            )
            scrubbed_0079 = Metrics0079.objects.get(pk=scrubbed.pk)
            preserved_0079 = Metrics0079.objects.get(pk=preserved.pk)

            self.assertEqual(scrubbed_0079.query_token_secret_ref, "")
            self.assertEqual(scrubbed_0079.writer_token_secret_ref, "")
            self.assertEqual(preserved_0079.query_token_secret_ref, VALID_SECRET_REF)
            self.assertEqual(preserved_0079.writer_token_secret_ref, "")

            table_name = Metrics0079._meta.db_table
            constraint_names = self._check_constraint_names(table_name)
            self.assertIn(QUERY_CONSTRAINT, constraint_names)
            self.assertIn(WRITER_CONSTRAINT, constraint_names)

            for field_name in (
                "query_token_secret_ref",
                "writer_token_secret_ref",
            ):
                with self.subTest(field=field_name):
                    with self.assertRaises(IntegrityError), transaction.atomic():
                        Metrics0079.objects.filter(pk=preserved.pk).update(
                            **{field_name: "plaintext-token"}
                        )

            apps_0078_reversed = self._migrate_to(self.migrate_from)
            Metrics0078Reversed = apps_0078_reversed.get_model(
                "netbox_proxbox", "ProxmoxMetricsInfluxDB"
            )
            still_scrubbed = Metrics0078Reversed.objects.get(pk=scrubbed.pk)

            self.assertEqual(still_scrubbed.query_token_secret_ref, "")
            self.assertEqual(still_scrubbed.writer_token_secret_ref, "")
            reversed_constraints = self._check_constraint_names(table_name)
            self.assertNotIn(QUERY_CONSTRAINT, reversed_constraints)
            self.assertNotIn(WRITER_CONSTRAINT, reversed_constraints)

            Metrics0078Reversed.objects.filter(pk=scrubbed.pk).update(
                query_token_secret_ref="accepted-only-after-reverse",
                writer_token_secret_ref="accepted-only-after-reverse",
            )
            unconstrained = Metrics0078Reversed.objects.get(pk=scrubbed.pk)
            self.assertEqual(
                unconstrained.query_token_secret_ref, "accepted-only-after-reverse"
            )
            self.assertEqual(
                unconstrained.writer_token_secret_ref, "accepted-only-after-reverse"
            )
        finally:
            self._migrate_to(self.migrate_to)
