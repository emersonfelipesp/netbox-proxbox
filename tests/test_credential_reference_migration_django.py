"""Real-Django migration gate for the additive credential reference."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOT = ROOT.parent / "netbox" / "netbox"
for candidate in (ROOT, NETBOX_ROOT):
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

require_django = os.environ.get("NETBOX_PROXBOX_REQUIRE_DJANGO", "").lower() in {
    "1",
    "true",
    "yes",
}
try:
    import django
except ModuleNotFoundError:
    if require_django:
        raise
    pytest.skip("Django/NetBox dependencies are unavailable", allow_module_level=True)

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")
try:
    django.setup()
except Exception as exc:
    if require_django:
        raise
    pytest.skip(
        f"NetBox test environment is unavailable: {exc}", allow_module_level=True
    )

from django.db import connection  # noqa: E402
from django.db.migrations.executor import MigrationExecutor  # noqa: E402
from django.test import TransactionTestCase  # noqa: E402

from tests.django_support import ForwardOnlyMigrationTestCase  # noqa: E402


class CredentialReferenceMigrationTest(TransactionTestCase):
    """Exercise populated upgrade, true rollback, reapply, and fresh state."""

    migrate_from = ("netbox_proxbox", "0095_standalone_vm_console")
    migrate_to = ("netbox_proxbox", "0097_add_cloudinit_credential_reference")
    target_column = "credential_reference_id"
    retained_column = "retained_credential_id"
    table = "netbox_proxbox_proxmoxvmcloudinit"

    def _migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.migrate([target])
        return executor.loader.project_state([target]).apps

    def _columns(self) -> set[str]:
        with connection.cursor() as cursor:
            return {
                column.name
                for column in connection.introspection.get_table_description(
                    cursor, self.table
                )
            }

    def _indexed_columns(self) -> set[tuple[str, ...]]:
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, self.table)
        return {
            tuple(constraint["columns"])
            for constraint in constraints.values()
            if constraint["index"]
        }

    def _retained_value(self, row_pk: int) -> int | None:
        quote_name = connection.ops.quote_name
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {quote_name(self.retained_column)} "
                f"FROM {quote_name(self.table)} WHERE id = %s",
                [row_pk],
            )
            return cursor.fetchone()[0]

    def test_populated_forward_reverse_reapply_and_serialization(self) -> None:
        try:
            apps = self._migrate(self.migrate_from)
            virtual_machine = apps.get_model(
                "virtualization", "VirtualMachine"
            ).objects.create(name="credential-migration-vm", status="active")
            cloud_init = apps.get_model(
                "netbox_proxbox", "ProxmoxVMCloudInit"
            ).objects.create(
                virtual_machine=virtual_machine,
                credential_reference_id=901,
            )
            with connection.schema_editor() as editor:
                editor.execute(
                    f"ALTER TABLE {editor.quote_name(self.table)} "
                    f"RENAME COLUMN {editor.quote_name(self.target_column)} "
                    f"TO {editor.quote_name(self.retained_column)}"
                )

            apps = self._migrate(self.migrate_to)
            columns = self._columns()
            self.assertIn(self.target_column, columns)
            self.assertIn(self.retained_column, columns)
            self.assertIn((self.target_column,), self._indexed_columns())
            migrated = apps.get_model(
                "netbox_proxbox", "ProxmoxVMCloudInit"
            ).objects.get(pk=cloud_init.pk)
            self.assertEqual(migrated.credential_reference_id, 901)

            from netbox_proxbox.api.serializers.vm_cloudinit import (
                ProxmoxVMCloudInitSerializer,
            )

            self.assertEqual(
                ProxmoxVMCloudInitSerializer(migrated).data[self.target_column],
                901,
            )

            self._migrate(self.migrate_from)
            self.assertNotIn(self.target_column, self._columns())
            self.assertIn(self.retained_column, self._columns())
            self.assertEqual(self._retained_value(cloud_init.pk), 901)

            apps = self._migrate(self.migrate_to)
            reapplied = apps.get_model(
                "netbox_proxbox", "ProxmoxVMCloudInit"
            ).objects.get(pk=cloud_init.pk)
            self.assertEqual(reapplied.credential_reference_id, 901)
            self.assertEqual(self._retained_value(cloud_init.pk), 901)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())

    def test_fresh_install_graph_runs_sanitized_source_before_additive_guard(
        self,
    ) -> None:
        executor = MigrationExecutor(connection)
        plan = executor.loader.graph.forwards_plan(self.migrate_to)
        self.assertLess(
            plan.index(("netbox_proxbox", "0064_proxmoxvmcloudinit_intent")),
            plan.index(self.migrate_to),
        )
        source = (
            ROOT / "netbox_proxbox" / "migrations" / "0064_proxmoxvmcloudinit_intent.py"
        ).read_text()
        self.assertIn('field_name="credential_reference_id"', source)


class CredentialReferenceFreshInstallTest(ForwardOnlyMigrationTestCase):
    """Prove a blank database can migrate through the sanitized source to leaf."""

    migration_floor = (
        "netbox_proxbox",
        "0097_add_cloudinit_credential_reference",
    )

    def test_zero_to_leaf_creates_the_generic_indexed_column(self) -> None:
        table = "netbox_proxbox_proxmoxvmcloudinit"
        with connection.cursor() as cursor:
            columns = {
                column.name
                for column in connection.introspection.get_table_description(
                    cursor, table
                )
            }
            constraints = connection.introspection.get_constraints(cursor, table)
        self.assertIn("credential_reference_id", columns)
        self.assertIn(
            ("credential_reference_id",),
            {
                tuple(constraint["columns"])
                for constraint in constraints.values()
                if constraint["index"]
            },
        )
