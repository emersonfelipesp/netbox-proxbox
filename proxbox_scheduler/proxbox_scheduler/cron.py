"""Cron expression evaluation for proxbox-scheduler.

Wraps ``croniter`` so the rest of the scheduler depends only on a tiny
``next_fire_time(expression, *, base, tz)`` function. Keeps croniter out
of the test surface for the runner / invoker modules.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from croniter import CroniterBadCronError, croniter


class CronError(ValueError):
    """Raised when a cron expression is malformed."""


def validate_expression(expression: str) -> None:
    """Raise :class:`CronError` if ``expression`` is not a valid 5-field cron."""
    try:
        croniter(expression)
    except (CroniterBadCronError, ValueError) as exc:
        raise CronError(f"Invalid cron expression: {expression!r} ({exc})") from exc


def next_fire_time(
    expression: str,
    *,
    base: datetime,
    tz: ZoneInfo,
) -> datetime:
    """Return the next datetime ``expression`` fires after ``base``, in ``tz``.

    ``base`` is interpreted in ``tz`` if it is naive. The return value is
    always timezone-aware in ``tz``.
    """
    if base.tzinfo is None:
        base = base.replace(tzinfo=tz)
    else:
        base = base.astimezone(tz)

    try:
        itr = croniter(expression, base)
    except (CroniterBadCronError, ValueError) as exc:
        raise CronError(f"Invalid cron expression: {expression!r} ({exc})") from exc

    next_dt = itr.get_next(datetime)
    if next_dt.tzinfo is None:
        next_dt = next_dt.replace(tzinfo=tz)
    return next_dt.astimezone(tz)
