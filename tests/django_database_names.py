"""Pure helpers for owned, reclaimable real-Django test database names."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import os
import re
import secrets
from hashlib import sha256

POSTGRES_IDENTIFIER_LIMIT = 63
HARNESS_DATABASE_PREFIX = "proxbox_h_"
_ROLE_CODES = {"foundation": "f", "template": "c", "test": "t"}
_DATABASE_NAME_RE = re.compile(
    rf"^{HARNESS_DATABASE_PREFIX}(?P<role>[fct])_"
    r"(?P<timestamp>\d{12})_(?P<pid>[1-9]\d{0,9})_"
    r"(?P<entropy>[0-9a-f]{10})_(?P<identity>[0-9a-f]{16})$"
)


@dataclass(frozen=True)
class HarnessDatabaseName:
    """Ownership fields encoded in one disposable database name."""

    name: str
    role: str
    run_nonce: str
    started_minute: datetime
    process_id: int


def make_run_nonce(
    *,
    process_id: int | None = None,
    worker_id: str | None = None,
    random_token: str | None = None,
    started_at: datetime | None = None,
) -> str:
    """Bind one harness namespace to UTC start time, PID, worker, and entropy."""

    process_id = os.getpid() if process_id is None else process_id
    if not 0 < process_id <= 2_147_483_647:
        raise ValueError(f"Invalid harness process ID: {process_id}")
    worker_id = (
        os.environ.get("PYTEST_XDIST_WORKER", "main")
        if worker_id is None
        else worker_id
    )
    random_token = secrets.token_hex(16) if random_token is None else random_token
    started_at = datetime.now(UTC) if started_at is None else started_at
    if started_at.tzinfo is None:
        raise ValueError("Harness start time must be timezone-aware")
    timestamp = started_at.astimezone(UTC).strftime("%Y%m%d%H%M")
    entropy = sha256(f"{worker_id}:{random_token}".encode()).hexdigest()[:10]
    return f"{timestamp}_{process_id}_{entropy}"


RUN_STARTED_AT = datetime.now(UTC).replace(microsecond=0)
RUN_NONCE = make_run_nonce(started_at=RUN_STARTED_AT)


def disposable_database_name(
    role: str,
    identity: str,
    *,
    run_nonce: str = RUN_NONCE,
) -> str:
    """Return a PostgreSQL-safe name unique to this harness and identity."""

    try:
        role_code = _ROLE_CODES[role]
    except KeyError as exc:
        raise ValueError(f"Unknown disposable database role: {role}") from exc
    identity_digest = sha256(identity.encode()).hexdigest()[:16]
    name = f"{HARNESS_DATABASE_PREFIX}{role_code}_{run_nonce}_{identity_digest}"
    if len(name) > POSTGRES_IDENTIFIER_LIMIT:
        raise ValueError(f"Disposable database name exceeds PostgreSQL limit: {name}")
    if parse_disposable_database_name(name) is None:
        raise ValueError(f"Invalid disposable database name: {name}")
    return name


def parse_disposable_database_name(name: str) -> HarnessDatabaseName | None:
    """Return trusted ownership fields from an exact harness database name."""

    match = _DATABASE_NAME_RE.fullmatch(name)
    if match is None:
        return None
    try:
        started_minute = datetime.strptime(
            match.group("timestamp"),
            "%Y%m%d%H%M",
        ).replace(tzinfo=UTC)
    except ValueError:
        return None
    process_id = int(match.group("pid"))
    if process_id > 2_147_483_647:
        return None
    run_nonce = "_".join(
        (match.group("timestamp"), match.group("pid"), match.group("entropy"))
    )
    roles_by_code = {code: role for role, code in _ROLE_CODES.items()}
    return HarnessDatabaseName(
        name=name,
        role=roles_by_code[match.group("role")],
        run_nonce=run_nonce,
        started_minute=started_minute,
        process_id=process_id,
    )


def advisory_lock_key(run_nonce: str) -> int:
    """Map one run nonce to PostgreSQL's signed-bigint advisory-lock space."""

    return int.from_bytes(sha256(run_nonce.encode()).digest()[:8], signed=True)
