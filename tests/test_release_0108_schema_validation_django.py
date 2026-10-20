"""Real PostgreSQL post-candidate validation and recorder-boundary controls."""

from __future__ import annotations

import os
import sys
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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

from django.db import (  # noqa: E402
    DatabaseError,
    IntegrityError,
    ProgrammingError,
    connection,
    transaction,
)
from django.db.migrations.executor import MigrationExecutor  # noqa: E402
from django.db.migrations.recorder import MigrationRecorder  # noqa: E402
from django.db.migrations.state import StateApps  # noqa: E402

from tests.django_support import ForwardOnlyMigrationTestCase  # noqa: E402


class ReleaseSchemaValidationTest(ForwardOnlyMigrationTestCase):
    """Reject malformed adoption without claiming or repairing its schema."""

    migrate_from = ("netbox_proxbox", "0107_v0_0_30_release")
    migrate_to = ("netbox_proxbox", "0108_v0_0_31_schema_validation")
    migration_floor = migrate_from
    endpoint_table = "netbox_proxbox_proxmoxendpoint"

    def _assert_unrecorded(self) -> None:
        self.assertTrue(
            MigrationRecorder(connection)
            .migration_qs.filter(app=self.migrate_from[0], name=self.migrate_from[1])
            .exists()
        )
        self.assertFalse(
            MigrationRecorder(connection)
            .migration_qs.filter(app=self.migrate_to[0], name=self.migrate_to[1])
            .exists()
        )

    def _ownership_case(self, column: str, extra_sql: str = "") -> None:
        apps = self._migrate_to(self.migrate_from)
        Endpoint = apps.get_model("netbox_proxbox", "ProxmoxEndpoint")
        endpoint = Endpoint.objects.create(name="semantic-adoption-preserved")
        with connection.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE netbox_proxbox_proxmoxendpoint "
                "DROP COLUMN netbox_cluster_id CASCADE"
            )
            cursor.execute(
                f"ALTER TABLE {connection.ops.quote_name(self.endpoint_table)} "
                f"ADD COLUMN netbox_cluster_id {column}"
            )
            if extra_sql:
                cursor.execute(extra_sql)
        validator = import_module("netbox_proxbox.migrations._release_0107_schema")
        with self.assertRaises(validator.ReleaseSchemaError):
            self._migrate_to(self.migrate_to)
        self._assert_unrecorded()
        self.assertEqual(Endpoint.objects.get(pk=endpoint.pk).name, endpoint.name)
        with connection.cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE {connection.ops.quote_name(self.endpoint_table)} "
                "DROP COLUMN netbox_cluster_id CASCADE"
            )
            cursor.execute(
                "ALTER TABLE netbox_proxbox_proxmoxendpoint "
                "ADD COLUMN netbox_cluster_id bigint NULL UNIQUE "
                "REFERENCES virtualization_cluster(id) DEFERRABLE INITIALLY DEFERRED"
            )
        self._migrate_to(self.migrate_to)
        self.assertEqual(Endpoint.objects.get(pk=endpoint.pk).name, endpoint.name)

    def test_missing_unique_is_refused_and_explicit_repair_allows_retry(self) -> None:
        self._ownership_case(
            "bigint NULL REFERENCES virtualization_cluster(id) DEFERRABLE INITIALLY DEFERRED"
        )

    def test_missing_foreign_key_is_refused(self) -> None:
        self._ownership_case("bigint NULL UNIQUE")

    def test_wrong_foreign_key_is_refused(self) -> None:
        self._ownership_case(
            "bigint NULL UNIQUE REFERENCES dcim_site(id) DEFERRABLE INITIALLY DEFERRED"
        )

    def test_unvalidated_foreign_key_is_refused(self) -> None:
        self._ownership_case(
            "bigint NULL UNIQUE",
            "ALTER TABLE netbox_proxbox_proxmoxendpoint "
            "ADD CONSTRAINT native_unvalidated FOREIGN KEY (netbox_cluster_id) "
            "REFERENCES virtualization_cluster(id) DEFERRABLE INITIALLY DEFERRED NOT VALID",
        )

    def test_partial_unique_is_refused(self) -> None:
        self._ownership_case(
            "bigint NULL",
            "CREATE UNIQUE INDEX native_partial ON "
            "netbox_proxbox_proxmoxendpoint(netbox_cluster_id) WHERE netbox_cluster_id > 0",
        )

    def test_composite_unique_is_refused(self) -> None:
        self._ownership_case(
            "bigint NULL",
            "CREATE UNIQUE INDEX native_composite ON "
            "netbox_proxbox_proxmoxendpoint(netbox_cluster_id, id)",
        )

    def test_expression_unique_is_refused(self) -> None:
        self._ownership_case(
            "bigint NULL",
            "CREATE UNIQUE INDEX native_expression ON "
            "netbox_proxbox_proxmoxendpoint((netbox_cluster_id + 0))",
        )

    def test_nulls_not_distinct_uniqueness_is_refused(self) -> None:
        if connection.pg_version < 150000:
            self.skipTest("NULLS NOT DISTINCT indexes require PostgreSQL 15 or newer")
        self._ownership_case(
            "bigint NULL",
            "CREATE UNIQUE INDEX native_nulls ON "
            "netbox_proxbox_proxmoxendpoint(netbox_cluster_id) NULLS NOT DISTINCT",
        )

    def test_incompatible_integer_width_is_refused(self) -> None:
        self._ownership_case("integer NULL UNIQUE")

    def test_incompatible_nullability_is_refused(self) -> None:
        self._ownership_case("bigint NOT NULL DEFAULT 0 UNIQUE")

    def test_failed_concurrent_unique_index_cannot_prove_ownership(self) -> None:
        apps = self._migrate_to(self.migrate_from)
        Endpoint = apps.get_model("netbox_proxbox", "ProxmoxEndpoint")
        Endpoint.objects.create(name="invalid-index-one")
        Endpoint.objects.create(name="invalid-index-two")
        with connection.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE netbox_proxbox_proxmoxendpoint DROP COLUMN netbox_cluster_id CASCADE"
            )
            cursor.execute(
                "ALTER TABLE netbox_proxbox_proxmoxendpoint ADD COLUMN netbox_cluster_id bigint NULL"
            )
            cursor.execute(
                "UPDATE netbox_proxbox_proxmoxendpoint SET netbox_cluster_id = 1"
            )
            with self.assertRaises(IntegrityError):
                cursor.execute(
                    "CREATE UNIQUE INDEX CONCURRENTLY native_invalid ON "
                    "netbox_proxbox_proxmoxendpoint(netbox_cluster_id)"
                )
            cursor.execute(
                "SELECT indisvalid FROM pg_index WHERE indexrelid = 'native_invalid'::regclass"
            )
            self.assertFalse(cursor.fetchone()[0])
        validator = import_module("netbox_proxbox.migrations._release_0107_schema")
        with self.assertRaisesRegex(validator.ReleaseSchemaError, "enforcing index"):
            self._migrate_to(self.migrate_to)
        self._assert_unrecorded()
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM netbox_proxbox_proxmoxendpoint WHERE netbox_cluster_id = 1"
            )
            self.assertEqual(cursor.fetchone()[0], 2)

    def _apply_unrecorded_release(self) -> StateApps:
        executor = MigrationExecutor(connection)
        state = executor.loader.project_state(
            self._migration_targets(executor, self.migrate_from)
        )
        migration = executor.loader.get_migration(*self.migrate_to)
        with connection.schema_editor() as editor:
            result = migration.apply(state, editor)
        self._assert_unrecorded()
        return result.apps

    def test_valid_complete_unrecorded_schema_is_adopted(self) -> None:
        self._apply_unrecorded_release()
        self._migrate_to(self.migrate_to)

    def test_physical_ownership_rejects_duplicate_and_dangling_ids(self) -> None:
        apps = self._migrate_to(self.migrate_to)
        Endpoint = apps.get_model("netbox_proxbox", "ProxmoxEndpoint")
        Native = apps.get_model("virtualization", "Cluster")
        NativeType = apps.get_model("virtualization", "ClusterType")
        kind = NativeType.objects.create(name="physical-owner", slug="physical-owner")
        native = Native.objects.create(name="physical-owner", type=kind)
        owner = Endpoint.objects.create(
            name="physical-owner", netbox_cluster_id=native.pk
        )
        other = Endpoint.objects.create(name="physical-other")
        Endpoint.objects.create(name="physical-unbound")
        self.assertEqual(Endpoint.objects.filter(netbox_cluster_id=None).count(), 2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Endpoint.objects.filter(pk=other.pk).update(netbox_cluster_id=native.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Endpoint.objects.filter(pk=other.pk).update(
                netbox_cluster_id=native.pk + 1000000
            )
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        self.assertEqual(Endpoint.objects.get(pk=owner.pk).netbox_cluster_id, native.pk)

    def _reject_adopted_service_schema(
        self, sql: str, expected: str, *, whole_function: bool = False
    ) -> None:
        self._apply_unrecorded_release()
        if whole_function:
            self._add_whole_row_function()
        with connection.cursor() as cursor:
            cursor.execute(sql)
        validator = import_module("netbox_proxbox.migrations._release_0107_schema")
        with self.assertRaisesRegex(validator.ReleaseSchemaError, expected):
            self._migrate_to(self.migrate_to)
        self._assert_unrecorded()

    def _add_whole_row_function(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE FUNCTION native_whole_owner(target netbox_proxbox_proxmoxendpoint) "
                "RETURNS bigint LANGUAGE plpgsql IMMUTABLE AS $$ "
                "BEGIN RETURN COALESCE(target.netbox_cluster_id, 0); END $$"
            )

    def test_whole_row_check_cannot_hide_owned_null_restriction(self) -> None:
        self._reject_adopted_service_schema(
            "ALTER TABLE netbox_proxbox_proxmoxendpoint ADD CONSTRAINT native_whole_check "
            "CHECK ((to_jsonb(netbox_proxbox_proxmoxendpoint)->>'netbox_cluster_id') IS NOT NULL)",
            "additional check or exclusion",
        )

    def test_mixed_whole_row_and_scalar_check_is_refused(self) -> None:
        self._reject_adopted_service_schema(
            "ALTER TABLE netbox_proxbox_proxmoxendpoint ADD CONSTRAINT native_mixed_check "
            "CHECK (native_whole_owner(netbox_proxbox_proxmoxendpoint) <> 0 AND name <> '')",
            "additional check or exclusion",
            whole_function=True,
        )

    def test_whole_row_unique_expression_is_refused(self) -> None:
        self._reject_adopted_service_schema(
            "CREATE UNIQUE INDEX native_whole_expression ON netbox_proxbox_proxmoxendpoint "
            "((native_whole_owner(netbox_proxbox_proxmoxendpoint)))",
            "additional unique enforcement",
            whole_function=True,
        )

    def test_whole_row_unique_predicate_is_refused(self) -> None:
        self._reject_adopted_service_schema(
            "CREATE UNIQUE INDEX native_whole_predicate ON netbox_proxbox_proxmoxendpoint(name) "
            "WHERE native_whole_owner(netbox_proxbox_proxmoxendpoint) = 0",
            "additional unique enforcement",
            whole_function=True,
        )

    def test_whole_row_exclusion_expression_is_refused(self) -> None:
        self._reject_adopted_service_schema(
            "ALTER TABLE netbox_proxbox_proxmoxendpoint ADD CONSTRAINT native_whole_exclusion "
            "EXCLUDE USING btree ((native_whole_owner(netbox_proxbox_proxmoxendpoint)) WITH =)",
            "additional check or exclusion",
            whole_function=True,
        )

    def test_whole_row_exclusion_predicate_is_refused(self) -> None:
        self._reject_adopted_service_schema(
            "ALTER TABLE netbox_proxbox_proxmoxendpoint ADD CONSTRAINT native_whole_exclusion_predicate "
            "EXCLUDE USING btree (name WITH =) "
            "WHERE (native_whole_owner(netbox_proxbox_proxmoxendpoint) = 0)",
            "additional check or exclusion",
            whole_function=True,
        )

    def test_unrelated_scalar_exclusion_remains_allowed(self) -> None:
        self._apply_unrecorded_release()
        with connection.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE netbox_proxbox_proxmoxendpoint ADD CONSTRAINT native_scalar_exclusion "
                "EXCLUDE USING btree ((lower(name)) WITH =)"
            )
        self._migrate_to(self.migrate_to)

    def test_unrelated_scalar_expression_with_table_dependency_remains_allowed(
        self,
    ) -> None:
        self._apply_unrecorded_release()
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE UNIQUE INDEX unrelated_scalar_name ON "
                "netbox_proxbox_proxmoxendpoint((lower(name)))"
            )
            cursor.execute(
                "SELECT count(*) FROM pg_depend WHERE "
                "classid = 'pg_class'::regclass "
                "AND objid = 'unrelated_scalar_name'::regclass "
                "AND refobjid = 'netbox_proxbox_proxmoxendpoint'::regclass "
                "AND refobjsubid = 0"
            )
            self.assertGreater(cursor.fetchone()[0], 0)
        self._migrate_to(self.migrate_to)

    def test_unrelated_scalar_function_check_remains_allowed(self) -> None:
        self._apply_unrecorded_release()
        with connection.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE netbox_proxbox_proxmoxendpoint ADD CONSTRAINT "
                "unrelated_scalar_check CHECK (length(name) > 0)"
            )
        self._migrate_to(self.migrate_to)

    def test_adopted_service_unique_constraint_is_required(self) -> None:
        self._reject_adopted_service_schema(
            "ALTER TABLE netbox_proxbox_proxmoxendpointservice DROP CONSTRAINT "
            "netbox_proxbox_endpointservice_unique_endpoint_name",
            "validated u constraint",
        )

    def test_adopted_credential_column_is_required(self) -> None:
        self._reject_adopted_service_schema(
            "ALTER TABLE netbox_proxbox_servicesshcredential DROP COLUMN username",
            "missing column username",
        )

    def test_adopted_service_field_type_is_required(self) -> None:
        self._reject_adopted_service_schema(
            "ALTER TABLE netbox_proxbox_proxmoxendpointservice ALTER COLUMN name TYPE text",
            "incompatible type",
        )

    def test_adopted_cloud_image_database_default_is_required(self) -> None:
        self._reject_adopted_service_schema(
            "ALTER TABLE netbox_proxbox_proxmoxendpoint ALTER COLUMN cloud_image_ssh_target_node DROP DEFAULT",
            "incompatible database default",
        )

    def test_good_unique_plus_nulls_not_distinct_is_refused(self) -> None:
        if connection.pg_version < 150000:
            self.skipTest("NULLS NOT DISTINCT indexes require PostgreSQL 15 or newer")
        self._reject_adopted_service_schema(
            "CREATE UNIQUE INDEX native_additional_nulls ON "
            "netbox_proxbox_proxmoxendpoint(netbox_cluster_id) NULLS NOT DISTINCT",
            "additional unique enforcement",
        )

    def test_good_ownership_plus_not_null_check_is_refused(self) -> None:
        self._reject_adopted_service_schema(
            "ALTER TABLE netbox_proxbox_proxmoxendpoint ADD CONSTRAINT "
            "native_additional_check CHECK (netbox_cluster_id IS NOT NULL)",
            "additional check or exclusion",
        )

    def test_good_service_keys_plus_unique_username_is_refused(self) -> None:
        self._reject_adopted_service_schema(
            "CREATE UNIQUE INDEX credential_additional_login ON "
            "netbox_proxbox_servicesshcredential(username)",
            "additional unique enforcement",
        )

    def test_extra_expression_uniqueness_on_owned_column_is_refused(self) -> None:
        self._reject_adopted_service_schema(
            "CREATE UNIQUE INDEX native_additional_expression ON "
            "netbox_proxbox_proxmoxendpoint((coalesce(netbox_cluster_id, 0)))",
            "additional unique enforcement",
        )

    def test_extra_predicate_dependency_on_owned_column_is_refused(self) -> None:
        self._reject_adopted_service_schema(
            "CREATE UNIQUE INDEX native_additional_predicate ON "
            "netbox_proxbox_proxmoxendpoint(name) WHERE netbox_cluster_id IS NULL",
            "additional unique enforcement",
        )

    def test_unrelated_existing_endpoint_enforcement_is_preserved(self) -> None:
        self._apply_unrecorded_release()
        with connection.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE netbox_proxbox_proxmoxendpoint ADD CONSTRAINT "
                "unrelated_name_policy CHECK (name <> '')"
            )
        self._migrate_to(self.migrate_to)

    def test_receipt_holds_locks_against_ordinary_and_concurrent_index_ddl(
        self,
    ) -> None:
        self._apply_unrecorded_release()
        validator = import_module("netbox_proxbox.migrations._release_0107_schema")
        original = validator.validate_release_schema

        def observe_locked_schema(apps: StateApps, editor: object) -> None:
            original(apps, editor)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                own_pid = cursor.fetchone()[0]
            other = connection.copy(alias=connection.alias)
            try:
                with other.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    self.assertNotEqual(own_pid, cursor.fetchone()[0])
                    cursor.execute("SET lock_timeout = '100ms'")
                    for variant in ("", "CONCURRENTLY "):
                        name = "receipt_concurrent" if variant else "receipt_ordinary"
                        with self.assertRaisesRegex(DatabaseError, "lock timeout"):
                            cursor.execute(
                                f"CREATE UNIQUE INDEX {variant}{name} ON "
                                "netbox_proxbox_servicesshcredential(username)"
                            )
            finally:
                other.close()

        with patch.object(validator, "validate_release_schema", observe_locked_schema):
            self._migrate_to(self.migrate_to)

    def test_busy_schema_lock_fails_bounded_and_retries_after_release(self) -> None:
        self._apply_unrecorded_release()
        other = connection.copy(alias=connection.alias)
        with connection.cursor() as cursor:
            cursor.execute("SHOW lock_timeout")
            original = cursor.fetchone()[0]
            cursor.execute("SELECT set_config('lock_timeout', '100ms', false)")
        try:
            other.set_autocommit(False)
            with other.cursor() as cursor:
                cursor.execute(
                    "LOCK TABLE netbox_proxbox_servicesshcredential "
                    "IN SHARE UPDATE EXCLUSIVE MODE"
                )
            with self.assertRaisesRegex(DatabaseError, "lock timeout"):
                self._migrate_to(self.migrate_to)
            self._assert_unrecorded()
        finally:
            other.rollback()
            other.close()
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('lock_timeout', %s, false)", [original]
                )
        self._migrate_to(self.migrate_to)

    def test_failure_in_deferred_ddl_rolls_back_and_retry_succeeds(self) -> None:
        executor = MigrationExecutor(connection)
        migration = executor.loader.get_migration(*self.migrate_to)
        operation = migration.operations[-1]
        original = operation.code

        def fail_deferred_ddl(apps: StateApps, editor: object) -> None:
            self.assertFalse(editor.deferred_sql)
            editor.deferred_sql.append(
                "ALTER TABLE netbox_proxbox_proxmoxendpoint ADD COLUMN validator_rollback_probe integer"
            )
            editor.deferred_sql.append(
                "SELECT proxbox_deliberately_missing_release_function()"
            )
            original(apps, editor)

        with patch.object(operation, "code", fail_deferred_ddl):
            with self.assertRaises(ProgrammingError):
                executor.migrate(self._migration_targets(executor, self.migrate_to))
        self._assert_unrecorded()
        with connection.cursor() as cursor:
            tables = connection.introspection.table_names(cursor)
        self.assertIn("netbox_proxbox_proxmoxendpointservice", tables)
        with connection.cursor() as cursor:
            columns = connection.introspection.get_table_description(
                cursor, self.endpoint_table
            )
        self.assertNotIn(
            "validator_rollback_probe", {column.name for column in columns}
        )
        self._migrate_to(self.migrate_to)

    def test_candidate_upgrade_reverse_and_reapply_preserve_existing_values(
        self,
    ) -> None:
        apps = self._migrate_to(self.migrate_from)
        Endpoint = apps.get_model("netbox_proxbox", "ProxmoxEndpoint")
        Service = apps.get_model("netbox_proxbox", "ProxmoxEndpointService")
        Credential = apps.get_model("netbox_proxbox", "ServiceSSHCredential")
        Native = apps.get_model("virtualization", "Cluster")
        Kind = apps.get_model("virtualization", "ClusterType")
        kind = Kind.objects.create(
            name="candidate-preserved", slug="candidate-preserved"
        )
        native = Native.objects.create(name="candidate-preserved", type=kind)
        endpoint = Endpoint.objects.create(
            name="candidate-preserved",
            netbox_cluster_id=native.pk,
            cloud_image_ssh_target_node="fixture-node",
            cloud_image_ssh_identity_file="/tmp/fixture-identity",
        )
        service = Service.objects.create(
            endpoint_id=endpoint.pk, name="ssh", protocol="tcp", ports=[22]
        )
        credential = Credential.objects.create(
            service_id=service.pk, username="fixture-user"
        )
        Endpoint.objects.filter(pk=endpoint.pk).update(ssh_service_id=service.pk)
        before = (
            Endpoint.objects.get(pk=endpoint.pk).__dict__.copy(),
            service.pk,
            credential.pk,
        )
        self._migrate_to(self.migrate_to)
        self._migrate_to(self.migrate_from)
        self._assert_unrecorded()
        self._migrate_to(self.migrate_to)
        after = Endpoint.objects.get(pk=endpoint.pk)
        self.assertEqual(after.netbox_cluster_id, before[0]["netbox_cluster_id"])
        self.assertEqual(after.ssh_service_id, before[1])
        self.assertEqual(after.cloud_image_ssh_target_node, "fixture-node")
        self.assertEqual(after.cloud_image_ssh_identity_file, "/tmp/fixture-identity")
        self.assertEqual(Credential.objects.get(pk=before[2]).username, "fixture-user")


class Production0106ValidationUpgradeTest(ForwardOnlyMigrationTestCase):
    """Distinguish the original schema commit from the later validation commit."""

    migrate_from = (
        "netbox_proxbox",
        "0106_device_sync_scope_and_netbox_token_approval",
    )
    migration_floor = migrate_from
    migrate_to = ("netbox_proxbox", "0108_v0_0_31_schema_validation")

    def test_production_upgrade_applies_both_and_preserves_backfilled_owner(
        self,
    ) -> None:
        apps = self._migrate_to(self.migrate_from)
        Endpoint = apps.get_model("netbox_proxbox", "ProxmoxEndpoint")
        Tracking = apps.get_model("netbox_proxbox", "ProxmoxCluster")
        Native = apps.get_model("virtualization", "Cluster")
        Kind = apps.get_model("virtualization", "ClusterType")
        kind = Kind.objects.create(
            name="production-preserved", slug="production-preserved"
        )
        native = Native.objects.create(name="production-preserved", type=kind)
        endpoint = Endpoint.objects.create(name="production-preserved")
        Tracking.objects.create(
            endpoint_id=endpoint.pk,
            netbox_cluster_id=native.pk,
            name="production-preserved",
        )
        final = self._migrate_to(self.migrate_to)
        self.assertEqual(
            final.get_model("netbox_proxbox", "ProxmoxEndpoint")
            .objects.get(pk=endpoint.pk)
            .netbox_cluster_id,
            native.pk,
        )
        applied = (
            MigrationRecorder(connection)
            .migration_qs.filter(app="netbox_proxbox")
            .values_list("name", flat=True)
        )
        self.assertIn("0107_v0_0_30_release", applied)
        self.assertIn("0108_v0_0_31_schema_validation", applied)

    def test_validation_failure_keeps_prior_schema_commit_and_then_retries(
        self,
    ) -> None:
        validator = import_module("netbox_proxbox.migrations._release_0107_schema")
        with patch.object(
            validator,
            "validate_release_schema",
            side_effect=validator.ReleaseSchemaError("fixture refusal"),
        ):
            with self.assertRaisesRegex(
                validator.ReleaseSchemaError, "fixture refusal"
            ):
                self._migrate_to(self.migrate_to)
        applied = (
            MigrationRecorder(connection)
            .migration_qs.filter(app="netbox_proxbox")
            .values_list("name", flat=True)
        )
        self.assertIn("0107_v0_0_30_release", applied)
        self.assertNotIn("0108_v0_0_31_schema_validation", applied)
        with connection.cursor() as cursor:
            self.assertIn(
                "netbox_proxbox_proxmoxendpointservice",
                connection.introspection.table_names(cursor),
            )
        self._migrate_to(self.migrate_to)
