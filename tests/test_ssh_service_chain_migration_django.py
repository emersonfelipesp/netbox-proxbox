"""Disposable-database coverage for the consolidated release migration."""

from __future__ import annotations

from importlib import import_module
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from tests.netbox_test_paths import netbox_source_roots


REPO_ROOT = Path(__file__).resolve().parents[1]
for candidate in (REPO_ROOT, *netbox_source_roots(REPO_ROOT)):
    candidate_string = str(candidate)
    if candidate.exists() and candidate_string not in sys.path:
        sys.path.insert(0, candidate_string)

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
    pytest.skip("Django is unavailable.", allow_module_level=True)

if not hasattr(django, "__path__"):
    pytest.skip("The mocked suite does not provide Django.", allow_module_level=True)

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:  # pragma: no cover - external harness availability
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is unavailable: {exc}", allow_module_level=True
    )

import django.db.models.deletion  # noqa: E402
from django.db import connection, migrations, models  # noqa: E402
from django.db.migrations.executor import MigrationExecutor  # noqa: E402
from django.db.migrations.recorder import MigrationRecorder  # noqa: E402
from netbox_proxbox.migrations import (  # noqa: E402
    _idempotent_ops as idempotent_ops,
)
from tests.django_support import ForwardOnlyMigrationTestCase  # noqa: E402


class SSHServiceChainMigrationTest(ForwardOnlyMigrationTestCase):
    """Prove clean, staging, rollback, and reapply migration paths."""

    migrate_from = (
        "netbox_proxbox",
        "0106_device_sync_scope_and_netbox_token_approval",
    )
    migration_floor = migrate_from
    migrate_to = ("netbox_proxbox", "0107_v0_0_30_release")
    legacy_migration_name = "0107_endpoint_native_cluster_binding"
    schema_tables = (
        "netbox_proxbox_proxmoxendpoint",
        "netbox_proxbox_proxmoxendpointservice",
        "netbox_proxbox_proxmoxendpointservice_ipaddresses",
        "netbox_proxbox_servicesshcredential",
    )

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.fresh_leaf_schema = cls._schema_signature()

    @classmethod
    def _schema_signature(cls) -> tuple:
        with connection.cursor() as cursor:
            existing = set(connection.introspection.table_names(cursor))
            signatures = []
            for table in cls.schema_tables:
                if table not in existing:
                    signatures.append((table, None, None))
                    continue
                columns = tuple(
                    sorted(
                        (column.name, column.type_code, column.null_ok)
                        for column in connection.introspection.get_table_description(
                            cursor, table
                        )
                    )
                )
                constraints = connection.introspection.get_constraints(cursor, table)
                normalized = tuple(
                    sorted(
                        (
                            name,
                            tuple(details.get("columns") or ()),
                            bool(details.get("primary_key")),
                            bool(details.get("unique")),
                            bool(details.get("index")),
                            tuple(details["foreign_key"])
                            if details.get("foreign_key")
                            else None,
                            bool(details.get("check")),
                        )
                        for name, details in constraints.items()
                    )
                )
                signatures.append((table, columns, normalized))
        return tuple(signatures)

    @staticmethod
    def _legacy_cluster_operation() -> migrations.AddField:
        return migrations.AddField(
            model_name="proxmoxendpoint",
            name="netbox_cluster",
            field=models.OneToOneField(
                to="virtualization.cluster",
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proxbox_endpoint",
                null=True,
                blank=True,
                editable=False,
                help_text=(
                    "Native NetBox cluster owned by this endpoint's synchronization."
                ),
            ),
        )

    def _apply_legacy_cluster_schema(self):
        executor = MigrationExecutor(connection)
        targets = self._migration_targets(executor, self.migrate_from)
        before = executor.loader.project_state(targets)
        after = before.clone()
        operation = self._legacy_cluster_operation()
        operation.state_forwards("netbox_proxbox", after)
        with connection.schema_editor() as schema_editor:
            operation.database_forwards("netbox_proxbox", schema_editor, before, after)
        MigrationRecorder(connection).record_applied(
            "netbox_proxbox", self.legacy_migration_name
        )
        return after.apps

    def _assert_release_columns_absent_after_reverse(self) -> None:
        endpoint_table = "netbox_proxbox_proxmoxendpoint"
        with connection.cursor() as cursor:
            tables = set(connection.introspection.table_names(cursor))
            columns = {
                column.name
                for column in connection.introspection.get_table_description(
                    cursor, endpoint_table
                )
            }
        self.assertIn("netbox_cluster_id", columns)
        self.assertNotIn("ssh_service_id", columns)
        self.assertNotIn("cloud_image_ssh_target_node", columns)
        self.assertNotIn("cloud_image_ssh_identity_file", columns)
        self.assertNotIn("cloud_image_ssh_binding_fingerprint", columns)
        self.assertNotIn("netbox_proxbox_proxmoxendpointservice", tables)
        self.assertNotIn("netbox_proxbox_proxmoxendpointservice_ipaddresses", tables)
        self.assertNotIn("netbox_proxbox_servicesshcredential", tables)

    def _assert_endpoint_service_fk(self) -> None:
        constraints = connection.introspection.get_constraints(
            connection.cursor(), "netbox_proxbox_proxmoxendpoint"
        )
        foreign_keys = {
            details["foreign_key"]
            for details in constraints.values()
            if details.get("columns") == ["ssh_service_id"]
        }
        self.assertIn(("netbox_proxbox_proxmoxendpointservice", "id"), foreign_keys)

    def test_forward_reverse_reapply_restores_the_foreign_key(self) -> None:
        apps_before = self._migrate_to(self.migrate_from)
        EndpointBefore = apps_before.get_model("netbox_proxbox", "ProxmoxEndpoint")
        endpoint = EndpointBefore.objects.create(name="ssh-chain-migration")

        apps_after = self._migrate_to(self.migrate_to)
        EndpointAfter = apps_after.get_model("netbox_proxbox", "ProxmoxEndpoint")
        ServiceAfter = apps_after.get_model("netbox_proxbox", "ProxmoxEndpointService")
        service = ServiceAfter.objects.create(
            endpoint_id=endpoint.pk,
            name="ssh",
            protocol="tcp",
            ports=[22],
        )
        EndpointAfter.objects.filter(pk=endpoint.pk).update(ssh_service_id=service.pk)
        self._assert_endpoint_service_fk()

        apps_rollback = self._migrate_to(self.migrate_from)
        EndpointRollback = apps_rollback.get_model("netbox_proxbox", "ProxmoxEndpoint")
        self.assertNotIn(
            "ssh_service",
            {field.name for field in EndpointRollback._meta.get_fields()},
        )
        self._assert_release_columns_absent_after_reverse()

        apps_reapplied = self._migrate_to(self.migrate_to)
        EndpointReapplied = apps_reapplied.get_model(
            "netbox_proxbox", "ProxmoxEndpoint"
        )
        ServiceReapplied = apps_reapplied.get_model(
            "netbox_proxbox", "ProxmoxEndpointService"
        )
        self.assertIsNone(EndpointReapplied.objects.get(pk=endpoint.pk).ssh_service_id)
        replacement = ServiceReapplied.objects.create(
            endpoint_id=endpoint.pk,
            name="ssh",
            protocol="tcp",
            ports=[22],
        )
        EndpointReapplied.objects.filter(pk=endpoint.pk).update(
            ssh_service_id=replacement.pk
        )
        self._assert_endpoint_service_fk()
        self.assertEqual(self._schema_signature(), self.fresh_leaf_schema)

    def test_staging_legacy_schema_converges_to_fresh_leaf(self) -> None:
        apps_before = self._migrate_to(self.migrate_from)
        Endpoint = apps_before.get_model("netbox_proxbox", "ProxmoxEndpoint")
        Tracking = apps_before.get_model("netbox_proxbox", "ProxmoxCluster")
        Native = apps_before.get_model("virtualization", "Cluster")
        NativeType = apps_before.get_model("virtualization", "ClusterType")
        native_type = NativeType.objects.create(
            name="staging-migration", slug="staging-migration"
        )
        endpoint = Endpoint.objects.create(name="staging-endpoint")
        cluster = Native.objects.create(name="staging-cluster", type=native_type)
        Tracking.objects.create(
            endpoint_id=endpoint.pk,
            netbox_cluster_id=cluster.pk,
            name="staging-evidence",
        )

        legacy_apps = self._apply_legacy_cluster_schema()
        release_migration = import_module(
            "netbox_proxbox.migrations.0107_v0_0_30_release"
        )
        release_migration.backfill_cluster_bindings(
            legacy_apps, SimpleNamespace(connection=connection)
        )
        LegacyEndpoint = legacy_apps.get_model("netbox_proxbox", "ProxmoxEndpoint")
        self.assertEqual(
            LegacyEndpoint.objects.get(pk=endpoint.pk).netbox_cluster_id,
            cluster.pk,
        )

        migrated = self._migrate_to(self.migrate_to)
        MigratedEndpoint = migrated.get_model("netbox_proxbox", "ProxmoxEndpoint")
        self.assertEqual(
            MigratedEndpoint.objects.get(pk=endpoint.pk).netbox_cluster_id,
            cluster.pk,
        )
        applied_names = set(
            MigrationRecorder(connection)
            .migration_qs.filter(app="netbox_proxbox")
            .values_list("name", flat=True)
        )
        self.assertIn(self.legacy_migration_name, applied_names)
        self.assertIn(self.migrate_to[1], applied_names)
        self.assertEqual(self._schema_signature(), self.fresh_leaf_schema)

    def test_clean_0106_upgrade_matches_empty_database_leaf(self) -> None:
        self._migrate_to(self.migrate_to)
        self.assertEqual(self._schema_signature(), self.fresh_leaf_schema)

    def test_failed_table_creation_rolls_back_and_retry_matches_fresh_leaf(
        self,
    ) -> None:
        before_signature = self._schema_signature()
        executor = MigrationExecutor(connection)
        migration = executor.loader.get_migration(*self.migrate_to)
        create_service = next(
            operation
            for operation in migration.operations
            if any(
                isinstance(state_operation, migrations.CreateModel)
                and state_operation.name == "ProxmoxEndpointService"
                for state_operation in operation.state_operations
            )
        )
        run_python = create_service.database_operations[0]
        original = run_python.code

        def fail_after_table_creation(apps, schema_editor) -> None:
            original(apps, schema_editor)
            tables = set(schema_editor.connection.introspection.table_names())
            self.assertIn("netbox_proxbox_proxmoxendpointservice", tables)
            self.assertIn("netbox_proxbox_proxmoxendpointservice_ipaddresses", tables)
            raise RuntimeError("injected failure after table creation")

        run_python.code = fail_after_table_creation
        try:
            with self.assertRaisesRegex(
                RuntimeError, "injected failure after table creation"
            ):
                executor.migrate(self._migration_targets(executor, self.migrate_to))
        finally:
            run_python.code = original

        self.assertFalse(
            MigrationRecorder(connection)
            .migration_qs.filter(app=self.migrate_to[0], name=self.migrate_to[1])
            .exists()
        )
        self.assertEqual(self._schema_signature(), before_signature)
        self._migrate_to(self.migrate_to)
        self.assertEqual(self._schema_signature(), self.fresh_leaf_schema)

    def test_reverse_tolerates_missing_autogenerated_m2m_table(self) -> None:
        apps_after = self._migrate_to(self.migrate_to)
        Service = apps_after.get_model("netbox_proxbox", "ProxmoxEndpointService")
        through = Service._meta.get_field("ipaddresses").remote_field.through
        with connection.schema_editor() as schema_editor:
            schema_editor.delete_model(through)
        with connection.cursor() as cursor:
            tables = set(connection.introspection.table_names(cursor))
        self.assertIn("netbox_proxbox_proxmoxendpointservice", tables)
        self.assertNotIn(through._meta.db_table, tables)

        self._migrate_to(self.migrate_from)
        self._assert_release_columns_absent_after_reverse()
        self._migrate_to(self.migrate_to)
        self.assertEqual(self._schema_signature(), self.fresh_leaf_schema)


def test_reverse_field_helper_is_explicitly_selected() -> None:
    """The default retained-column policy stays unchanged for published users."""
    assert idempotent_ops.add_field_idempotent.__kwdefaults__ == {
        "preserve_default": True,
        "remove_on_reverse": False,
    }
