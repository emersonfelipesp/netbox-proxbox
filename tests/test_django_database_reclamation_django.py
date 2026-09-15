"""PostgreSQL integration coverage for migration-harness database reclamation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.django_database_names import disposable_database_name, make_run_nonce
from tests.test_proxmox_endpoint_allowed_tenants import _require_harness


@pytest.mark.django_db(transaction=True)
def test_reclaims_only_an_old_expired_lease_after_its_lock_is_free(
    pytestconfig: pytest.Config,
) -> None:
    _require_harness(pytestconfig)
    from django.db import connection

    from tests.django_database_reclamation import (
        acquire_run_lock,
        open_maintenance_connection,
        reclaim_stale_harness_databases,
    )

    now = datetime(2026, 9, 15, 12, 30, tzinfo=UTC)
    created_at = now - timedelta(hours=3)
    current_nonce, current_database = _database_identity("current", created_at)
    expired_nonce, expired_database = _database_identity("expired", created_at)
    maintenance_connection = open_maintenance_connection(connection)
    current_owner_connection = open_maintenance_connection(connection)
    try:
        acquire_run_lock(current_owner_connection, current_nonce)
        _create_commented_database(
            maintenance_connection,
            current_database,
            created_at=created_at,
            lease_until=now + timedelta(minutes=10),
            hostname="another-runner",
        )
        _create_commented_database(
            maintenance_connection,
            expired_database,
            created_at=created_at,
            lease_until=now - timedelta(minutes=1),
            hostname="another-runner",
        )

        current_owner_connection.close()
        reclaimed = reclaim_stale_harness_databases(
            maintenance_connection,
            now=now,
        )

        assert reclaimed == [expired_database]
        assert _existing_databases(
            maintenance_connection,
            current_database,
            expired_database,
        ) == {current_database}
    finally:
        current_owner_connection.close()
        _drop_databases(
            maintenance_connection,
            current_database,
            expired_database,
        )
        maintenance_connection.close()


@pytest.mark.django_db(transaction=True)
def test_renewal_extends_the_persisted_lease(pytestconfig: pytest.Config) -> None:
    _require_harness(pytestconfig)
    from django.db import connection

    from tests.django_database_reclamation import (
        DEFAULT_LEASE_DURATION,
        HarnessLeaseManager,
        acquire_run_lock,
        open_maintenance_connection,
        parse_harness_database_owner,
    )

    now = datetime(2026, 9, 15, 12, 30, tzinfo=UTC)
    created_at = now - timedelta(hours=3)
    run_nonce, database_name = _database_identity("renew", created_at)
    maintenance_connection = open_maintenance_connection(connection)
    lease_manager = HarnessLeaseManager(maintenance_connection, run_nonce)
    try:
        acquire_run_lock(maintenance_connection, run_nonce)
        _create_commented_database(
            maintenance_connection,
            database_name,
            created_at=created_at,
            lease_until=now + timedelta(minutes=1),
        )
        lease_manager.register_database(database_name)

        lease_manager.renew_now(now=now)

        comment = _database_comment(maintenance_connection, database_name)
        owner = parse_harness_database_owner(database_name, comment)
        assert owner is not None
        assert owner.lease_until == now + DEFAULT_LEASE_DURATION
    finally:
        lease_manager.stop()
        _drop_databases(maintenance_connection, database_name)
        maintenance_connection.close()


@pytest.mark.django_db(transaction=True)
def test_lost_background_renewal_fails_the_next_setup_gate(
    pytestconfig: pytest.Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_harness(pytestconfig)
    from django.db import connection

    from tests.django_database_reclamation import (
        HarnessLeaseError,
        HarnessLeaseManager,
        acquire_run_lock,
        open_maintenance_connection,
    )

    now = datetime.now(UTC)
    run_nonce, database_name = _database_identity("lost-renewal", now)
    blocked_database = disposable_database_name(
        "test",
        "blocked-after-lost-renewal",
        run_nonce=run_nonce,
    )
    owner_connection = open_maintenance_connection(connection)
    cleanup_connection = open_maintenance_connection(connection)
    lease_manager = HarnessLeaseManager(
        owner_connection,
        run_nonce,
        lease_duration=timedelta(seconds=2),
        renewal_interval=timedelta(milliseconds=50),
    )
    try:
        acquire_run_lock(owner_connection, run_nonce)
        _create_commented_database(
            cleanup_connection,
            database_name,
            created_at=now,
            lease_until=now + timedelta(seconds=2),
        )
        lease_manager.register_database(database_name)
        lease_manager.start()

        owner_connection.close()

        assert lease_manager.wait_for_failure(3)
        from tests import django_support

        monkeypatch.setattr(
            django_support,
            "_HARNESS_LEASE_MANAGER",
            lease_manager,
        )
        with pytest.raises(
            HarnessLeaseError,
            match=(
                "Django harness lease protection was lost; refusing to create a new "
                "migration database"
            ),
        ):
            django_support.ForwardOnlyMigrationTestCase._create_database(
                blocked_database
            )
        assert _existing_databases(cleanup_connection, blocked_database) == set()
    finally:
        lease_manager.stop()
        owner_connection.close()
        _drop_databases(cleanup_connection, database_name)
        cleanup_connection.close()


def _database_identity(label: str, created_at: datetime) -> tuple[str, str]:
    run_nonce = make_run_nonce(
        process_id=2_147_483_640,
        worker_id=f"{label}-test",
        started_at=created_at,
    )
    database_name = disposable_database_name(
        "test",
        f"{label}-reclamation-test",
        run_nonce=run_nonce,
    )
    return run_nonce, database_name


def _create_commented_database(
    maintenance_connection: object,
    database_name: str,
    **comment_fields: object,
) -> None:
    from psycopg import sql

    from tests.django_database_reclamation import comment_harness_database

    with maintenance_connection.cursor() as cursor:  # type: ignore[attr-defined]
        cursor.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
        )
        comment_harness_database(cursor, database_name, **comment_fields)


def _database_comment(maintenance_connection: object, database_name: str) -> object:
    with maintenance_connection.cursor() as cursor:  # type: ignore[attr-defined]
        cursor.execute(
            "SELECT shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE datname = %s",
            (database_name,),
        )
        return cursor.fetchone()[0]


def _existing_databases(
    maintenance_connection: object,
    *database_names: str,
) -> set[str]:
    with maintenance_connection.cursor() as cursor:  # type: ignore[attr-defined]
        cursor.execute(
            "SELECT datname FROM pg_database WHERE datname = ANY(%s)",
            (list(database_names),),
        )
        return {row[0] for row in cursor.fetchall()}


def _drop_databases(maintenance_connection: object, *database_names: str) -> None:
    from psycopg import sql

    with maintenance_connection.cursor() as cursor:  # type: ignore[attr-defined]
        for database_name in database_names:
            cursor.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )
