"""Common fixtures for the proxbox-scheduler test suite."""

from __future__ import annotations

from zoneinfo import ZoneInfo

import pytest

from proxbox_scheduler.config import ModeKind, SchedulerConfig, SchedulerMode


@pytest.fixture()
def utc() -> ZoneInfo:
    return ZoneInfo("UTC")


@pytest.fixture()
def base_config(utc: ZoneInfo) -> SchedulerConfig:
    return SchedulerConfig(
        mode=SchedulerMode(kind=ModeKind.OFF),
        invoke="http",
        timezone=utc,
        backoff_seconds=0.0,
        log_level="INFO",
        log_json=False,
        proxbox_api_url="http://proxbox-api.test",
        proxbox_api_key="testkey",
        proxbox_api_timeout=10.0,
        proxbox_api_verify_ssl=False,
        exec_command=["echo", "ok"],
    )
