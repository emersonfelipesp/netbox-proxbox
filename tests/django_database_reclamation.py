"""Durable ownership and reclamation for migration-harness databases."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import logging
import os
import socket
from threading import Event, Lock, Thread
from typing import Any

import psycopg
from psycopg import sql

from tests.django_database_names import (
    HARNESS_DATABASE_PREFIX,
    RUN_NONCE,
    RUN_STARTED_AT,
    advisory_lock_key,
    parse_disposable_database_name,
)

COMMENT_MARKER = "netbox-proxbox-django-harness"
COMMENT_VERSION = 2
DEFAULT_STALE_AFTER = timedelta(hours=2)
DEFAULT_LEASE_DURATION = timedelta(minutes=15)
DEFAULT_RENEWAL_INTERVAL = timedelta(seconds=60)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HarnessDatabaseOwner:
    """Validated ownership metadata for one harness database."""

    run_nonce: str
    process_id: int
    created_at: datetime
    lease_until: datetime
    hostname: str
    lock_key: int


class HarnessLeaseError(RuntimeError):
    """The harness can no longer prove exclusive ownership of its databases."""


class HarnessLeaseManager:
    """Renew database leases while retaining the run's advisory-lock session."""

    def __init__(
        self,
        maintenance_connection: Any,
        run_nonce: str = RUN_NONCE,
        *,
        lease_duration: timedelta = DEFAULT_LEASE_DURATION,
        renewal_interval: timedelta = DEFAULT_RENEWAL_INTERVAL,
    ) -> None:
        if renewal_interval <= timedelta(0):
            raise ValueError("Harness lease renewal interval must be positive")
        if lease_duration <= renewal_interval:
            raise ValueError("Harness lease duration must exceed its renewal interval")
        self._connection = maintenance_connection
        self._run_nonce = run_nonce
        self._lease_duration = lease_duration
        self._renewal_interval = renewal_interval
        self._database_names: set[str] = set()
        self._database_lock = Lock()
        self._connection_lock = Lock()
        self._state_lock = Lock()
        self._stop_event = Event()
        self._failure_event = Event()
        self._failure: str | None = None
        self._thread: Thread | None = None

    def start(self) -> None:
        """Verify protection and start the daemon renewal thread."""

        self.assert_healthy()
        if self._thread is not None:
            return
        self._thread = Thread(
            target=self._renewal_loop,
            name="proxbox-django-harness-lease",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop lease renewal before the owning connection is closed."""

        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()

    def register_database(self, database_name: str) -> None:
        """Add a newly commented database to subsequent renewal cycles."""

        self._raise_if_failed()
        with self._database_lock:
            self._raise_if_failed()
            self._database_names.add(database_name)

    def unregister_database(self, database_name: str) -> None:
        """Stop renewing a database before normal cleanup drops it."""

        with self._database_lock:
            self._database_names.discard(database_name)

    def assert_healthy(self) -> None:
        """Fail before a clone when the lock session or renewer was lost."""

        self._raise_if_failed()
        try:
            with self._connection_lock:
                verify_run_lock(self._connection, self._run_nonce)
            self._raise_if_failed()
        except Exception as exc:
            if isinstance(exc, HarnessLeaseError):
                raise
            self._record_failure("ownership-lock health check", exc)
            raise HarnessLeaseError(self._failure_message()) from exc

    def renew_now(self, *, now: datetime | None = None) -> None:
        """Renew every registered database immediately."""

        self._raise_if_failed()
        now = datetime.now(UTC) if now is None else now
        try:
            with self._connection_lock:
                self._raise_if_failed()
                verify_run_lock(self._connection, self._run_nonce)
                with self._database_lock:
                    renew_harness_database_leases(
                        self._connection,
                        sorted(self._database_names),
                        run_nonce=self._run_nonce,
                        lease_until=now + self._lease_duration,
                    )
        except Exception as exc:
            self._record_failure("lease renewal", exc)
            raise HarnessLeaseError(self._failure_message()) from exc

    def wait_for_failure(self, timeout: float) -> bool:
        """Wait until the background renewer records lost protection."""

        return self._failure_event.wait(timeout)

    def _renewal_loop(self) -> None:
        interval_seconds = self._renewal_interval.total_seconds()
        while not self._stop_event.wait(interval_seconds):
            try:
                self.renew_now()
            except HarnessLeaseError:
                return

    def _raise_if_failed(self) -> None:
        with self._state_lock:
            failed = self._failure is not None
        if failed:
            raise HarnessLeaseError(self._failure_message())

    def _record_failure(self, operation: str, exc: Exception) -> None:
        detail = f"{operation} failed: {type(exc).__name__}: {exc}"
        with self._state_lock:
            if self._failure is None:
                self._failure = detail
                logger.error("Django harness protection lost: %s", detail)
        self._failure_event.set()

    def _failure_message(self) -> str:
        with self._state_lock:
            detail = self._failure or "unknown lease failure"
        return (
            "Django harness lease protection was lost; refusing to create a new "
            f"migration database ({detail})"
        )


def open_maintenance_connection(django_connection: Any):
    """Open an autocommit PostgreSQL connection outside disposable databases."""

    parameters = django_connection.get_connection_params()
    parameters["dbname"] = "postgres"
    return psycopg.connect(**parameters, autocommit=True)


def harness_database_comment(
    database_name: str,
    *,
    created_at: datetime = RUN_STARTED_AT,
    lease_until: datetime | None = None,
    hostname: str | None = None,
) -> str:
    """Serialize exact session ownership and its renewable lease."""

    parsed_name = parse_disposable_database_name(database_name)
    if parsed_name is None:
        raise ValueError(f"Not a harness database name: {database_name}")
    lease_until = (
        datetime.now(UTC) + DEFAULT_LEASE_DURATION
        if lease_until is None
        else lease_until
    )
    if created_at.tzinfo is None:
        raise ValueError("Harness database creation time must be timezone-aware")
    if lease_until.tzinfo is None:
        raise ValueError("Harness database lease time must be timezone-aware")
    payload = {
        "created_at": _utc_string(created_at),
        "hostname": socket.gethostname() if hostname is None else hostname,
        "lease_until": _utc_string(lease_until),
        "lock_key": advisory_lock_key(parsed_name.run_nonce),
        "marker": COMMENT_MARKER,
        "owner_id": parsed_name.run_nonce,
        "pid": parsed_name.process_id,
        "version": COMMENT_VERSION,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def comment_harness_database(
    cursor: Any,
    database_name: str,
    *,
    created_at: datetime = RUN_STARTED_AT,
    lease_until: datetime | None = None,
    hostname: str | None = None,
) -> None:
    """Persist the current run's ownership marker on a created database."""

    cursor.execute(
        sql.SQL("COMMENT ON DATABASE {} IS %s").format(sql.Identifier(database_name)),
        (
            harness_database_comment(
                database_name,
                created_at=created_at,
                lease_until=lease_until,
                hostname=hostname,
            ),
        ),
    )


def parse_harness_database_owner(
    database_name: str,
    comment: object,
) -> HarnessDatabaseOwner | None:
    """Validate a comment against the ownership encoded in its database name."""

    parsed_name = parse_disposable_database_name(database_name)
    if parsed_name is None or not isinstance(comment, str):
        return None
    try:
        payload = json.loads(comment)
        created_at = _parse_utc_string(payload["created_at"])
        lease_until = _parse_utc_string(payload["lease_until"])
    except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    expected_keys = {
        "created_at",
        "hostname",
        "lease_until",
        "lock_key",
        "marker",
        "owner_id",
        "pid",
        "version",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        return None
    if not isinstance(payload["hostname"], str):
        return None
    owner = HarnessDatabaseOwner(
        run_nonce=payload["owner_id"],
        process_id=payload["pid"],
        created_at=created_at,
        lease_until=lease_until,
        hostname=payload["hostname"],
        lock_key=payload["lock_key"],
    )
    if not _owner_matches_name(owner, parsed_name, payload):
        return None
    return owner


def _owner_matches_name(
    owner: HarnessDatabaseOwner, parsed_name: Any, payload: dict
) -> bool:
    return bool(
        payload["marker"] == COMMENT_MARKER
        and type(payload["version"]) is int
        and payload["version"] == COMMENT_VERSION
        and type(owner.run_nonce) is str
        and type(owner.process_id) is int
        and type(owner.lock_key) is int
        and owner.hostname
        and owner.run_nonce == parsed_name.run_nonce
        and owner.process_id == parsed_name.process_id
        and owner.lock_key == advisory_lock_key(owner.run_nonce)
        and owner.created_at.replace(second=0, microsecond=0)
        == parsed_name.started_minute
        and owner.lease_until >= owner.created_at
    )


def renew_harness_database_leases(
    maintenance_connection: Any,
    database_names: Sequence[str],
    *,
    run_nonce: str,
    lease_until: datetime,
) -> None:
    """Extend leases only for databases still owned by this exact run."""

    if lease_until.tzinfo is None:
        raise ValueError("Harness database lease time must be timezone-aware")
    with maintenance_connection.cursor() as cursor:
        for database_name in database_names:
            owner = _read_database_owner(cursor, database_name)
            if owner is None or owner.run_nonce != run_nonce:
                raise RuntimeError(
                    f"Harness database ownership marker changed: {database_name}"
                )
            comment_harness_database(
                cursor,
                database_name,
                created_at=owner.created_at,
                lease_until=lease_until,
                hostname=owner.hostname,
            )


def verify_run_lock(maintenance_connection: Any, run_nonce: str) -> None:
    """Require the maintenance session to retain this run's advisory lock."""

    lock_key = advisory_lock_key(run_nonce)
    with maintenance_connection.cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS ("
            "SELECT 1 FROM pg_locks "
            "WHERE locktype = 'advisory' AND pid = pg_backend_pid() AND granted "
            "AND classid = ((%s::bigint >> 32) & 4294967295)::oid "
            "AND objid = (%s::bigint & 4294967295)::oid AND objsubid = 1"
            ")",
            (lock_key, lock_key),
        )
        if not cursor.fetchone()[0]:
            raise RuntimeError(f"Harness ownership lock was lost: {run_nonce}")


def reclaim_stale_harness_databases(
    maintenance_connection: Any,
    *,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
    now: datetime | None = None,
) -> list[str]:
    """Drop only old databases with expired leases and free ownership locks."""

    if stale_after <= timedelta(0):
        raise ValueError("Harness database stale threshold must be positive")
    now = datetime.now(UTC) if now is None else now
    if now.tzinfo is None:
        raise ValueError("Harness reclamation time must be timezone-aware")
    now = now.astimezone(UTC)
    with maintenance_connection.cursor() as cursor:
        cursor.execute(
            "SELECT datname, shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE datname LIKE %s ORDER BY datname",
            (f"{HARNESS_DATABASE_PREFIX}%",),
        )
        candidates = cursor.fetchall()
    reclaimed = []
    for database_name, comment in candidates:
        owner = parse_harness_database_owner(database_name, comment)
        reason = _keep_reason(owner, stale_after, now)
        if reason is not None:
            logger.info("Keeping harness database %s: %s", database_name, reason)
            continue
        if _reclaim_unlocked_database(
            maintenance_connection,
            database_name,
            owner,
            stale_after=stale_after,
            now=now,
        ):
            reclaimed.append(database_name)
    return reclaimed


def _keep_reason(
    owner: HarnessDatabaseOwner | None,
    stale_after: timedelta,
    now: datetime,
) -> str | None:
    if owner is None:
        return "ownership or lease metadata is missing, malformed, or obsolete"
    if now - owner.created_at <= stale_after:
        return "the database has not reached the minimum reclamation age"
    if owner.lease_until > now:
        return f"the owner lease remains valid until {owner.lease_until.isoformat()}"
    return None


def _reclaim_unlocked_database(
    maintenance_connection: Any,
    database_name: str,
    owner: HarnessDatabaseOwner,
    *,
    stale_after: timedelta,
    now: datetime,
) -> bool:
    lock_acquired = False
    try:
        with maintenance_connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (owner.lock_key,))
            lock_acquired = cursor.fetchone()[0]
            if not lock_acquired:
                logger.info(
                    "Keeping harness database %s: its ownership lock is held",
                    database_name,
                )
                return False
            current_owner = _read_database_owner(cursor, database_name)
            reason = _keep_reason(current_owner, stale_after, now)
            if reason is not None or current_owner != owner:
                detail = reason or "the ownership metadata changed during reclamation"
                logger.info("Keeping harness database %s: %s", database_name, detail)
                return False
            cursor.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )
            logger.info("Reclaimed harness database %s", database_name)
            return True
    except Exception as exc:
        logger.warning(
            "Keeping harness database %s because reclamation was uncertain: %s: %s",
            database_name,
            type(exc).__name__,
            exc,
        )
        return False
    finally:
        if lock_acquired:
            _release_reclamation_lock(maintenance_connection, owner.lock_key)


def _read_database_owner(
    cursor: Any, database_name: str
) -> HarnessDatabaseOwner | None:
    cursor.execute(
        "SELECT shobj_description(oid, 'pg_database') "
        "FROM pg_database WHERE datname = %s",
        (database_name,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return parse_harness_database_owner(database_name, row[0])


def _release_reclamation_lock(maintenance_connection: Any, lock_key: int) -> None:
    try:
        with maintenance_connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
    except Exception as exc:
        logger.warning(
            "Could not release harness reclamation lock %s: %s: %s",
            lock_key,
            type(exc).__name__,
            exc,
        )


def acquire_run_lock(maintenance_connection: Any, run_nonce: str = RUN_NONCE) -> None:
    """Hold one session-level ownership lock until the harness exits."""

    with maintenance_connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_try_advisory_lock(%s)", (advisory_lock_key(run_nonce),)
        )
        if not cursor.fetchone()[0]:
            raise RuntimeError(f"Harness ownership lock is already held: {run_nonce}")


def _utc_string(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_utc_string(value: object) -> datetime:
    if not isinstance(value, str):
        raise TypeError("UTC timestamp must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("UTC timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reclaim stale netbox-proxbox Django harness databases."
    )
    parser.add_argument(
        "--reclaim",
        action="store_true",
        help="drop old owned databases only after lease expiry and lock release",
    )
    arguments = parser.parse_args(argv)
    if not arguments.reclaim:
        parser.error("--reclaim is required")
    return arguments


def main(argv: Sequence[str] | None = None) -> int:
    """Run reclamation without pytest after Django settings are configured."""

    _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")
    import django

    django.setup()
    from django.db import connection

    maintenance_connection = open_maintenance_connection(connection)
    try:
        reclaimed = reclaim_stale_harness_databases(maintenance_connection)
    finally:
        maintenance_connection.close()
    print(f"Reclaimed {len(reclaimed)} stale harness database(s).")
    for database_name in reclaimed:
        print(database_name)
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entry point
    raise SystemExit(main())
