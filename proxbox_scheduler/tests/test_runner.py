"""Runner-loop tests using fake sleeper / clock — no real sleeping."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

import pytest

from proxbox_scheduler.config import ModeKind, SchedulerConfig, SchedulerMode
from proxbox_scheduler.invoker import InvokeResult
from proxbox_scheduler.runner import SchedulerRunner


class _CountingInvoker:
    def __init__(self, results: list[InvokeResult]) -> None:
        self._results = list(results)
        self.calls: int = 0

    def trigger(self) -> InvokeResult:
        self.calls += 1
        if self._results:
            return self._results.pop(0)
        return InvokeResult.ok("default")


class _RecordingSleeper:
    def __init__(
        self, on_call: Callable[["_RecordingSleeper", float], None] | None = None
    ) -> None:
        self.sleeps: list[float] = []
        self._on_call = on_call

    def __call__(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        if self._on_call is not None:
            self._on_call(self, seconds)


def _make_off_config(base_config: SchedulerConfig) -> SchedulerConfig:
    return replace(base_config, mode=SchedulerMode(kind=ModeKind.OFF))


def _make_continuous_config(
    base_config: SchedulerConfig, *, backoff: float = 0.0
) -> SchedulerConfig:
    return replace(
        base_config,
        mode=SchedulerMode(kind=ModeKind.CONTINUOUS),
        backoff_seconds=backoff,
    )


def _make_interval_config(
    base_config: SchedulerConfig, *, seconds: int, backoff: float = 0.0
) -> SchedulerConfig:
    return replace(
        base_config,
        mode=SchedulerMode(kind=ModeKind.INTERVAL, interval_seconds=seconds),
        backoff_seconds=backoff,
    )


def _make_cron_config(
    base_config: SchedulerConfig,
    *,
    expression: str,
    tz: str = "UTC",
    backoff: float = 0.0,
) -> SchedulerConfig:
    return replace(
        base_config,
        mode=SchedulerMode(kind=ModeKind.CRON, cron_expression=expression),
        timezone=ZoneInfo(tz),
        backoff_seconds=backoff,
    )


class TestOffMode:
    def test_off_mode_does_not_trigger(self, base_config: SchedulerConfig) -> None:
        inv = _CountingInvoker([])
        runner = SchedulerRunner(
            config=_make_off_config(base_config),
            invoker=inv,
            sleeper=_RecordingSleeper(),
        )
        runner.run()
        assert inv.calls == 0


class TestContinuousMode:
    def test_fires_back_to_back_until_stopped(
        self, base_config: SchedulerConfig
    ) -> None:
        inv = _CountingInvoker([InvokeResult.ok(), InvokeResult.ok()])

        def stop_after_two(s: _RecordingSleeper, _seconds: float) -> None:
            pass  # no sleeping in continuous-success path

        sleeper = _RecordingSleeper(on_call=stop_after_two)
        runner = SchedulerRunner(
            config=_make_continuous_config(base_config),
            invoker=inv,
            sleeper=sleeper,
        )

        # Stop after the third call so we observe back-to-back firing
        # without an inter-trigger sleep.
        original_trigger = inv.trigger

        def trigger_and_maybe_stop() -> InvokeResult:
            result = original_trigger()
            if inv.calls >= 3:
                runner.stop()
            return result

        inv.trigger = trigger_and_maybe_stop  # type: ignore[assignment]
        runner.run()

        assert inv.calls == 3
        assert sleeper.sleeps == []  # no backoff because all succeeded

    def test_backoff_applied_only_on_failure(
        self, base_config: SchedulerConfig
    ) -> None:
        inv = _CountingInvoker(
            [InvokeResult.ok(), InvokeResult.failed("nope"), InvokeResult.ok()]
        )
        sleeper = _RecordingSleeper()
        runner = SchedulerRunner(
            config=_make_continuous_config(base_config, backoff=15.0),
            invoker=inv,
            sleeper=sleeper,
        )

        original_trigger = inv.trigger

        def trigger_and_maybe_stop() -> InvokeResult:
            result = original_trigger()
            if inv.calls >= 3:
                runner.stop()
            return result

        inv.trigger = trigger_and_maybe_stop  # type: ignore[assignment]
        runner.run()

        assert inv.calls == 3
        assert sleeper.sleeps == [15.0]


class TestIntervalMode:
    def test_sleeps_between_triggers(self, base_config: SchedulerConfig) -> None:
        inv = _CountingInvoker([InvokeResult.ok(), InvokeResult.ok()])
        sleeper = _RecordingSleeper()
        runner = SchedulerRunner(
            config=_make_interval_config(base_config, seconds=60),
            invoker=inv,
            sleeper=sleeper,
        )

        original_trigger = inv.trigger

        def trigger_and_maybe_stop() -> InvokeResult:
            result = original_trigger()
            if inv.calls >= 2:
                runner.stop()
            return result

        inv.trigger = trigger_and_maybe_stop  # type: ignore[assignment]
        runner.run()

        assert inv.calls == 2
        # First slot sleeps; loop stops before computing second slot.
        assert len(sleeper.sleeps) == 1
        slept = sleeper.sleeps[0]
        # The trigger is near-instantaneous in tests, so we should be close to 60s.
        assert 50.0 <= slept <= 60.0

    def test_interval_failure_triggers_backoff(
        self, base_config: SchedulerConfig
    ) -> None:
        inv = _CountingInvoker([InvokeResult.failed("boom")])
        sleeper = _RecordingSleeper()
        runner = SchedulerRunner(
            config=_make_interval_config(base_config, seconds=30, backoff=10.0),
            invoker=inv,
            sleeper=sleeper,
        )

        original_trigger = inv.trigger

        def trigger_and_maybe_stop() -> InvokeResult:
            result = original_trigger()
            runner.stop()
            return result

        inv.trigger = trigger_and_maybe_stop  # type: ignore[assignment]
        runner.run()

        assert inv.calls == 1
        # Backoff sleep happens, then the remaining-slot sleep happens.
        assert sleeper.sleeps[0] == 10.0


class TestCronMode:
    def test_cron_sleeps_until_next_fire_then_triggers(
        self, base_config: SchedulerConfig
    ) -> None:
        inv = _CountingInvoker([InvokeResult.ok()])
        sleeper = _RecordingSleeper()
        tz = ZoneInfo("UTC")
        # Pretend the current time is 10:30 UTC; "0 */4 * * *" → next fire is 12:00.
        fake_now = datetime(2026, 5, 13, 10, 30, tzinfo=tz)
        clock_calls = {"n": 0}

        def fake_clock() -> datetime:
            clock_calls["n"] += 1
            return fake_now

        runner = SchedulerRunner(
            config=_make_cron_config(base_config, expression="0 */4 * * *"),
            invoker=inv,
            sleeper=sleeper,
            clock=fake_clock,
        )

        original_trigger = inv.trigger

        def trigger_and_stop() -> InvokeResult:
            result = original_trigger()
            runner.stop()
            return result

        inv.trigger = trigger_and_stop  # type: ignore[assignment]
        runner.run()

        assert inv.calls == 1
        assert len(sleeper.sleeps) == 1
        # 10:30 → 12:00 = 5400 seconds.
        assert sleeper.sleeps[0] == pytest.approx(5400.0, abs=1.0)

    def test_cron_can_stop_during_wait(self, base_config: SchedulerConfig) -> None:
        inv = _CountingInvoker([])
        tz = ZoneInfo("UTC")
        fake_now = datetime(2026, 5, 13, 10, 30, tzinfo=tz)

        def fake_clock() -> datetime:
            return fake_now

        # Sleep handler: stop the runner mid-sleep so it never triggers.
        runner_holder: dict[str, SchedulerRunner] = {}

        def stop_during_sleep(_s: _RecordingSleeper, _seconds: float) -> None:
            runner_holder["r"].stop()

        sleeper = _RecordingSleeper(on_call=stop_during_sleep)
        runner = SchedulerRunner(
            config=_make_cron_config(base_config, expression="0 */4 * * *"),
            invoker=inv,
            sleeper=sleeper,
            clock=fake_clock,
        )
        runner_holder["r"] = runner

        runner.run()

        assert inv.calls == 0
        assert len(sleeper.sleeps) == 1
