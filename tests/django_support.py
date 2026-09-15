"""Shared helpers for tests running against a real NetBox database."""

from __future__ import annotations

import atexit
from collections.abc import Iterable
import os
from time import monotonic
from typing import Any

from django.apps import apps as global_apps
from django.contrib.auth import get_user_model
from django.core.management.sql import emit_post_migrate_signal
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.state import ModelState, ProjectState
from django.test import TransactionTestCase
from users.models import Token

from tests.django_database_names import RUN_NONCE, disposable_database_name
from tests.django_database_reclamation import (
    HarnessLeaseManager,
    acquire_run_lock,
    comment_harness_database,
    open_maintenance_connection,
    reclaim_stale_harness_databases,
)


_CREATED_DATABASES: set[str] = set()
_HARNESS_SESSION_CONNECTION: Any | None = None
_HARNESS_LEASE_MANAGER: HarnessLeaseManager | None = None


def make_user(
    username: str,
    *,
    password: str | None = None,
    email: str = "",
    is_staff: bool = False,
    is_superuser: bool = False,
    permissions: Iterable[Any] = (),
):
    """Create a NetBox user, then persist manager-incompatible flags."""

    user = get_user_model().objects.create_user(username=username, password=password)
    field_names = {field.name for field in user._meta.fields}
    updates = {"email": email, "is_superuser": is_superuser}
    if "is_staff" in field_names:
        updates["is_staff"] = is_staff
    for field_name, value in updates.items():
        setattr(user, field_name, value)
    user.save(update_fields=tuple(updates))
    grant_user_permissions(user, permissions)
    return user


def grant_user_permissions(user: Any, permissions: Iterable[Any]) -> None:
    """Grant Django model permissions across NetBox's user-model rename."""

    permission_items = tuple(permissions)
    if not permission_items:
        return
    permission_manager = getattr(user, "permissions", None)
    if permission_manager is None:
        permission_manager = user.user_permissions
    permission_manager.add(*permission_items)


def make_api_token(user: Any) -> tuple[Token, dict[str, str]]:
    """Create a current-format NetBox token and its authentication header."""

    token = Token.objects.create(user=user)
    headers = {
        "HTTP_AUTHORIZATION": f"{token.get_auth_header_prefix()}{token.token}",
    }
    return token, headers


def raw_update_fields(model: type, pk: object, **updates: object) -> None:
    """Inject legacy or corrupt state without exercising guarded model writers."""

    quote_name = connection.ops.quote_name
    table_name = quote_name(model._meta.db_table)
    assignments = ", ".join(
        f"{quote_name(model._meta.get_field(field_name).column)} = %s"
        for field_name in updates
    )
    pk_column = quote_name(model._meta.pk.column)
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {table_name} SET {assignments} WHERE {pk_column} = %s",  # nosec B608
            [*updates.values(), pk],
        )


class ForwardOnlyMigrationTestCase(TransactionTestCase):
    """Clone a class-level historical database for each migration test."""

    migration_floor: tuple[str, str] | None = None
    _foundation_database: str | None = None
    _foundation_floor: tuple[str, str] | None = None
    _pending_template_classes: set[type] | None = None
    _foundation_migration_seconds: float | None = None

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._primary_database = str(connection.settings_dict["NAME"])
        executor = MigrationExecutor(connection)
        cls._resolved_migration_floor = cls.resolve_migration_floor(executor)
        cls._template_database = disposable_database_name(
            "template",
            f"{cls.__module__}.{cls.__qualname__}",
        )
        cls._class_cleanup_complete = False
        cls.addClassCleanup(cls._drop_template_database)
        cls._ensure_foundation_database()
        cls._create_database(
            cls._template_database,
            template=ForwardOnlyMigrationTestCase._foundation_database,
        )
        cls._switch_default_database(cls._template_database)
        try:
            executor = MigrationExecutor(connection)
            cls._migrate_with_post_migrate(
                executor,
                cls._migration_targets(executor, cls._resolved_migration_floor),
            )
        finally:
            cls._switch_default_database(cls._primary_database)

    @classmethod
    def tearDownClass(cls) -> None:
        """Drop class-owned databases before Django releases the test class."""

        try:
            cls._drop_template_database()
        finally:
            super().tearDownClass()

    @classmethod
    def resolve_migration_floor(
        cls,
        executor: MigrationExecutor,
    ) -> tuple[str, str]:
        """Return the earliest plugin state needed by this test class."""

        del executor
        if cls.migration_floor is None:
            raise AssertionError(f"{cls.__name__}.migration_floor must be configured")
        return cls.migration_floor

    @classmethod
    def _ensure_foundation_database(cls) -> None:
        base = ForwardOnlyMigrationTestCase
        if base._foundation_database is not None:
            return
        _ensure_harness_session()
        executor = MigrationExecutor(connection)
        template_classes = set(base.__subclasses__())
        class_floors = {
            template_class: template_class.resolve_migration_floor(executor)
            for template_class in template_classes
        }
        foundation_floor = min(
            class_floors.values(),
            key=lambda target: len(executor.loader.graph.forwards_plan(target)),
        )
        cls._assert_foundation_precedes_class_floors(
            executor,
            foundation_floor,
            class_floors.values(),
        )
        foundation_database = disposable_database_name(
            "foundation",
            f"{cls._primary_database}:{foundation_floor}",
        )
        cls._switch_default_database("postgres")
        try:
            cls._create_database(foundation_database)
        finally:
            cls._switch_default_database(cls._primary_database)
        cls._switch_default_database(foundation_database)
        started = monotonic()
        try:
            executor = MigrationExecutor(connection)
            cls._migrate_with_post_migrate(
                executor,
                cls._migration_targets(executor, foundation_floor),
            )
        except Exception:
            cls._switch_default_database(cls._primary_database)
            cls._drop_database(foundation_database)
            raise
        migration_seconds = monotonic() - started
        cls._switch_default_database(cls._primary_database)
        base._foundation_database = foundation_database
        base._foundation_floor = foundation_floor
        base._pending_template_classes = template_classes
        base._foundation_migration_seconds = migration_seconds
        if os.environ.get("NETBOX_PROXBOX_MIGRATION_TIMINGS") == "1":
            print(  # noqa: T201
                f"PROXBOX_CLEAN_FOUNDATION_MIGRATION_SECONDS={migration_seconds:.3f}",
                flush=True,
            )

    @staticmethod
    def _assert_foundation_precedes_class_floors(
        executor: MigrationExecutor,
        foundation_floor: tuple[str, str],
        class_floors: Iterable[tuple[str, str]],
    ) -> None:
        for class_floor in class_floors:
            if foundation_floor not in executor.loader.graph.forwards_plan(class_floor):
                raise AssertionError(
                    f"Migration floor {class_floor} does not descend from "
                    f"suite foundation {foundation_floor}"
                )

    @staticmethod
    def _migrate_with_post_migrate(
        executor: MigrationExecutor,
        targets: list[tuple[str, str]],
    ) -> ProjectState:
        """Migrate and emit the historical post-migrate state like Django."""

        plan = executor.migration_plan(targets)
        post_migrate_state = executor.migrate(targets, plan=plan)
        post_migrate_state.clear_delayed_apps_cache()
        post_migrate_apps = post_migrate_state.apps
        with post_migrate_apps.bulk_update():
            model_keys = []
            for model_state in post_migrate_apps.real_models:
                model_key = model_state.app_label, model_state.name_lower
                model_keys.append(model_key)
                post_migrate_apps.unregister_model(*model_key)
        post_migrate_apps.render_multiple(
            [
                ModelState.from_model(global_apps.get_model(*model_key))
                for model_key in model_keys
            ]
        )
        emit_post_migrate_signal(
            verbosity=0,
            interactive=False,
            db=connection.alias,
            apps=post_migrate_apps,
            plan=plan,
        )
        ForwardOnlyMigrationTestCase._remove_future_plugin_content_types(
            post_migrate_apps
        )
        return post_migrate_state

    @staticmethod
    def _remove_future_plugin_content_types(post_migrate_apps: Any) -> None:
        """Remove current-code ObjectType parents beyond the historical floor."""

        app_label = "netbox_proxbox"
        ContentType = post_migrate_apps.get_model("contenttypes", "ContentType")
        historical_models = {
            model._meta.model_name
            for model in post_migrate_apps.get_app_config(app_label).get_models()
        }
        ContentType.objects.using(connection.alias).filter(app_label=app_label).exclude(
            model__in=historical_models
        ).delete()

    @classmethod
    def _create_database(cls, database_name: str, template: str | None = None) -> None:
        _assert_harness_protection()
        if database_name in _CREATED_DATABASES:
            raise AssertionError(f"Disposable database already exists: {database_name}")
        quoted_database = connection.ops.quote_name(database_name)
        with connection.cursor() as cursor:
            if template is None:
                cursor.execute(f"CREATE DATABASE {quoted_database}")  # nosec B608
            else:
                quoted_template = connection.ops.quote_name(template)
                cursor.execute(  # nosec B608
                    f"CREATE DATABASE {quoted_database} TEMPLATE {quoted_template}"
                )
            _CREATED_DATABASES.add(database_name)
            comment_harness_database(cursor, database_name)
        _register_database_lease(database_name)

    @staticmethod
    def _switch_default_database(database_name: str) -> None:
        """Rebind the default alias after closing its prior PostgreSQL pool."""

        connection.close()
        close_pool = getattr(connection, "close_pool", None)
        if close_pool is not None:
            close_pool()
        connection.settings_dict["NAME"] = database_name
        connection.connect()

    @classmethod
    def _drop_template_database(cls) -> None:
        if cls._class_cleanup_complete:
            return
        cls._class_cleanup_complete = True
        cls._switch_default_database(cls._primary_database)
        cls._drop_database(cls._template_database)
        base = ForwardOnlyMigrationTestCase
        if base._pending_template_classes is None:
            cls._close_default_connection()
            return
        base._pending_template_classes.discard(cls)
        if not base._pending_template_classes and base._foundation_database is not None:
            cls._drop_database(base._foundation_database)
            base._foundation_database = None
            base._foundation_floor = None
            base._pending_template_classes = None
            base._foundation_migration_seconds = None
        cls._close_default_connection()

    @staticmethod
    def _close_default_connection() -> None:
        connection.close()
        close_pool = getattr(connection, "close_pool", None)
        if close_pool is not None:
            close_pool()

    @staticmethod
    def _drop_database(database_name: str) -> None:
        if database_name not in _CREATED_DATABASES:
            return
        _unregister_database_lease(database_name)
        quoted_database = connection.ops.quote_name(database_name)
        try:
            with connection.cursor() as cursor:
                cursor.execute(  # nosec B608
                    f"DROP DATABASE IF EXISTS {quoted_database} WITH (FORCE)"
                )
        except Exception:
            _register_database_lease(database_name)
            raise
        _CREATED_DATABASES.discard(database_name)

    def setUp(self) -> None:
        super().setUp()
        self._migration_database = disposable_database_name("test", self.id())
        self._create_database(
            self._migration_database,
            template=self._template_database,
        )
        self.addCleanup(self._drop_migration_database)
        self._switch_default_database(self._migration_database)
        executor = MigrationExecutor(connection)
        targets = self._migration_targets(executor, self._resolved_migration_floor)
        self.migration_apps = executor.loader.project_state(targets).apps
        self._current_migration_target = self._resolved_migration_floor

    def _drop_migration_database(self) -> None:
        self._switch_default_database(self._primary_database)
        self._drop_database(self._migration_database)

    def _fixture_teardown(self) -> None:
        """The dropped clone contains every write; the shared database stayed clean."""

    def _migrate_to(self, target: tuple[str, str]):
        if target == self._current_migration_target:
            return self.migration_apps
        executor = MigrationExecutor(connection)
        targets = self._migration_targets(executor, target)
        executor.migrate(targets)
        self.migration_apps = executor.loader.project_state(targets).apps
        self._current_migration_target = target
        return self.migration_apps

    @staticmethod
    def _migration_targets(
        executor: MigrationExecutor,
        plugin_target: tuple[str, str],
    ) -> list[tuple[str, str]]:
        """Keep dependencies current while moving only Proxbox through history."""

        return [
            plugin_target,
            *ForwardOnlyMigrationTestCase._dependency_leaves(
                executor,
                plugin_target[0],
            ),
        ]

    @staticmethod
    def _dependency_leaves(
        executor: MigrationExecutor,
        excluded_app: str,
    ) -> list[tuple[str, str]]:
        return sorted(
            leaf
            for leaf in executor.loader.graph.leaf_nodes()
            if leaf[0] != excluded_app
        )

    @staticmethod
    def _restore_current_leaf() -> None:
        """Leave cleanup to the isolated-database teardown without reversing 0092."""


def _ensure_harness_session() -> None:
    """Acquire durable ownership and reclaim databases from dead old runs."""

    global _HARNESS_LEASE_MANAGER, _HARNESS_SESSION_CONNECTION
    if _HARNESS_SESSION_CONNECTION is not None:
        _assert_harness_protection()
        return
    maintenance_connection = open_maintenance_connection(connection)
    try:
        acquire_run_lock(maintenance_connection, RUN_NONCE)
        reclaim_stale_harness_databases(maintenance_connection)
        lease_manager = HarnessLeaseManager(maintenance_connection)
        lease_manager.start()
    except Exception:
        maintenance_connection.close()
        raise
    _HARNESS_SESSION_CONNECTION = maintenance_connection
    _HARNESS_LEASE_MANAGER = lease_manager


def _assert_harness_protection() -> None:
    """Refuse a database clone after the lock session or renewer fails."""

    if _HARNESS_LEASE_MANAGER is None:
        raise RuntimeError("Django harness lease manager was not initialized")
    _HARNESS_LEASE_MANAGER.assert_healthy()


def _register_database_lease(database_name: str) -> None:
    if _HARNESS_LEASE_MANAGER is None:
        raise RuntimeError("Django harness lease manager was not initialized")
    _HARNESS_LEASE_MANAGER.register_database(database_name)


def _unregister_database_lease(database_name: str) -> None:
    if _HARNESS_LEASE_MANAGER is not None:
        _HARNESS_LEASE_MANAGER.unregister_database(database_name)


def _close_harness_session() -> None:
    """Release the advisory ownership lock after owned databases are gone."""

    global _HARNESS_LEASE_MANAGER, _HARNESS_SESSION_CONNECTION
    if _HARNESS_SESSION_CONNECTION is None:
        return
    if _HARNESS_LEASE_MANAGER is not None:
        _HARNESS_LEASE_MANAGER.stop()
        _HARNESS_LEASE_MANAGER = None
    _HARNESS_SESSION_CONNECTION.close()
    _HARNESS_SESSION_CONNECTION = None


def _drop_registered_databases_at_exit() -> None:
    """Best-effort cleanup for interrupted classes and test processes."""

    if not _CREATED_DATABASES:
        _close_harness_session()
        return
    original_database = str(connection.settings_dict["NAME"])
    try:
        ForwardOnlyMigrationTestCase._switch_default_database("postgres")
        for database_name in tuple(sorted(_CREATED_DATABASES)):
            try:
                ForwardOnlyMigrationTestCase._drop_database(database_name)
            except Exception:
                continue
    except Exception:
        pass
    finally:
        ForwardOnlyMigrationTestCase._close_default_connection()
        connection.settings_dict["NAME"] = original_database
        _close_harness_session()


atexit.register(_drop_registered_databases_at_exit)
