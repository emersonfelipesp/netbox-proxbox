"""Environment-driven configuration for proxbox-scheduler.

All knobs are read once at startup and frozen into an immutable
``SchedulerConfig`` dataclass. There is no plugin settings / DB lookup —
this container is intentionally stateless.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ModeKind(str, Enum):
    OFF = "off"
    INTERVAL = "interval"
    CONTINUOUS = "continuous"
    CRON = "cron"


class ConfigError(ValueError):
    """Raised when PROXBOX_MODE or any required env var is invalid."""


@dataclass(frozen=True)
class SchedulerMode:
    kind: ModeKind
    interval_seconds: int | None = None
    cron_expression: str | None = None

    def __post_init__(self) -> None:
        if self.kind is ModeKind.INTERVAL:
            if self.interval_seconds is None or self.interval_seconds <= 0:
                raise ConfigError("interval mode requires a positive integer of seconds")
        if self.kind is ModeKind.CRON:
            if not self.cron_expression:
                raise ConfigError("cron mode requires a non-empty cron expression")


InvokeKind = Literal["http", "exec"]


@dataclass(frozen=True)
class SchedulerConfig:
    mode: SchedulerMode
    invoke: InvokeKind
    timezone: ZoneInfo
    backoff_seconds: float
    log_level: str
    log_json: bool

    # HTTP-invoker knobs
    proxbox_api_url: str | None
    proxbox_api_key: str | None
    proxbox_api_timeout: float
    proxbox_api_verify_ssl: bool

    # Exec-invoker knobs
    exec_command: list[str] = field(default_factory=list)


_TRUTHY = {"1", "true", "yes", "on", "y", "t"}
_FALSY = {"0", "false", "no", "off", "n", "f", ""}


def _parse_bool(raw: str | None, *, default: bool) -> bool:
    if raw is None:
        return default
    lowered = raw.strip().lower()
    if lowered in _TRUTHY:
        return True
    if lowered in _FALSY:
        return False
    raise ConfigError(f"Unrecognized boolean value: {raw!r}")


def parse_mode(raw: str | None) -> SchedulerMode:
    """Parse the ``PROXBOX_MODE`` env value.

    Accepted forms (case-insensitive on the keyword, value preserved):

        off
        continuous
        interval=<int seconds>
        cron=<5-field expression>
    """
    if raw is None:
        return SchedulerMode(kind=ModeKind.OFF)

    value = raw.strip()
    if not value:
        return SchedulerMode(kind=ModeKind.OFF)

    lowered = value.lower()

    if lowered == "off":
        return SchedulerMode(kind=ModeKind.OFF)
    if lowered == "continuous":
        return SchedulerMode(kind=ModeKind.CONTINUOUS)

    if "=" not in value:
        raise ConfigError(
            f"Invalid PROXBOX_MODE={value!r}; "
            "expected off | continuous | interval=<sec> | cron=<expr>"
        )

    keyword, _, payload = value.partition("=")
    keyword = keyword.strip().lower()
    payload = payload.strip()

    if keyword == "interval":
        try:
            seconds = int(payload)
        except ValueError as exc:
            raise ConfigError(
                f"interval mode requires an integer number of seconds, got {payload!r}"
            ) from exc
        return SchedulerMode(kind=ModeKind.INTERVAL, interval_seconds=seconds)

    if keyword == "cron":
        return SchedulerMode(kind=ModeKind.CRON, cron_expression=payload)

    raise ConfigError(
        f"Unknown PROXBOX_MODE keyword {keyword!r}; expected interval or cron"
    )


def _parse_tz(raw: str | None) -> ZoneInfo:
    name = (raw or "UTC").strip() or "UTC"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ConfigError(f"Unknown timezone: {name!r}") from exc


def _parse_invoke(raw: str | None) -> InvokeKind:
    name = (raw or "http").strip().lower()
    if name not in ("http", "exec"):
        raise ConfigError(
            f"PROXBOX_SCHEDULER_INVOKE must be 'http' or 'exec', got {name!r}"
        )
    return name  # type: ignore[return-value]


def _parse_exec_command(raw: str | None) -> list[str]:
    if not raw:
        return [
            "python",
            "manage.py",
            "proxbox_sync",
            "--wait",
            "--enqueue-once",
        ]
    import shlex

    parts = shlex.split(raw)
    if not parts:
        raise ConfigError("PROXBOX_SCHEDULER_EXEC_CMD must contain at least one token")
    return parts


def load_config(env: dict[str, str] | None = None) -> SchedulerConfig:
    """Build a frozen ``SchedulerConfig`` from the supplied env mapping.

    Defaults to ``os.environ`` so the runtime entrypoint can call ``load_config()``
    with no arguments; tests can pass a synthetic mapping.
    """
    if env is None:
        env = dict(os.environ)

    mode = parse_mode(env.get("PROXBOX_MODE"))
    invoke = _parse_invoke(env.get("PROXBOX_SCHEDULER_INVOKE"))
    tz = _parse_tz(env.get("PROXBOX_SCHEDULER_TZ"))

    backoff_raw = env.get("PROXBOX_SCHEDULER_BACKOFF_ON_ERROR_SECONDS", "30")
    try:
        backoff = float(backoff_raw)
        if backoff < 0:
            raise ValueError
    except ValueError as exc:
        raise ConfigError(
            f"PROXBOX_SCHEDULER_BACKOFF_ON_ERROR_SECONDS must be a non-negative number, got {backoff_raw!r}"
        ) from exc

    log_level = env.get("PROXBOX_SCHEDULER_LOG_LEVEL", "INFO").strip().upper() or "INFO"
    log_json = _parse_bool(env.get("PROXBOX_SCHEDULER_LOG_JSON"), default=True)

    proxbox_api_url = env.get("PROXBOX_API_URL") or None
    proxbox_api_key = env.get("PROXBOX_API_KEY") or None
    api_timeout_raw = env.get("PROXBOX_API_TIMEOUT", "7200")
    try:
        api_timeout = float(api_timeout_raw)
        if api_timeout <= 0:
            raise ValueError
    except ValueError as exc:
        raise ConfigError(
            f"PROXBOX_API_TIMEOUT must be a positive number, got {api_timeout_raw!r}"
        ) from exc
    verify_ssl = _parse_bool(env.get("PROXBOX_API_VERIFY_SSL"), default=True)

    exec_cmd = _parse_exec_command(env.get("PROXBOX_SCHEDULER_EXEC_CMD"))

    if mode.kind is not ModeKind.OFF and invoke == "http":
        if not proxbox_api_url:
            raise ConfigError(
                "HTTP invocation requires PROXBOX_API_URL (e.g. http://proxbox-api:8000)"
            )

    return SchedulerConfig(
        mode=mode,
        invoke=invoke,
        timezone=tz,
        backoff_seconds=backoff,
        log_level=log_level,
        log_json=log_json,
        proxbox_api_url=proxbox_api_url,
        proxbox_api_key=proxbox_api_key,
        proxbox_api_timeout=api_timeout,
        proxbox_api_verify_ssl=verify_ssl,
        exec_command=exec_cmd,
    )
