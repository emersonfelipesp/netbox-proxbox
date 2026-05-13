"""Cron expression evaluation tests."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from proxbox_scheduler.cron import CronError, next_fire_time, validate_expression


def test_validate_accepts_valid_expression() -> None:
    validate_expression("0 */4 * * *")
    validate_expression("*/5 * * * *")


def test_validate_rejects_garbage() -> None:
    with pytest.raises(CronError):
        validate_expression("not a cron")


def test_next_fire_returns_future_time_in_tz() -> None:
    tz = ZoneInfo("UTC")
    base = datetime(2026, 5, 13, 10, 30, tzinfo=tz)
    result = next_fire_time("0 */4 * * *", base=base, tz=tz)
    assert result.tzinfo is not None
    assert result.tzinfo.key == "UTC"
    assert result > base
    # 4-hour cron after 10:30 → 12:00.
    assert result.hour == 12
    assert result.minute == 0


def test_next_fire_naive_base_is_interpreted_in_tz() -> None:
    tz = ZoneInfo("America/Sao_Paulo")
    naive = datetime(2026, 5, 13, 10, 30)  # naive
    result = next_fire_time("0 12 * * *", base=naive, tz=tz)
    assert result.tzinfo is not None
    assert result.tzinfo.key == "America/Sao_Paulo"
    assert result.hour == 12
    assert result.minute == 0


def test_next_fire_crosses_dst_safely() -> None:
    # America/Sao_Paulo no longer observes DST, but the call must still
    # succeed without crashing for any IANA zone.
    tz = ZoneInfo("Europe/London")
    base = datetime(2026, 3, 28, 23, 30, tzinfo=tz)  # right before BST start
    result = next_fire_time("30 1 * * *", base=base, tz=tz)
    assert result > base


def test_invalid_expression_raises_at_call_time() -> None:
    tz = ZoneInfo("UTC")
    base = datetime(2026, 5, 13, 10, 30, tzinfo=tz)
    with pytest.raises(CronError):
        next_fire_time("invalid", base=base, tz=tz)
