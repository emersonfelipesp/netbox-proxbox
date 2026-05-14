"""Main scheduler loop for proxbox-scheduler.

The runner is intentionally minimal: it dispatches on
:class:`~proxbox_scheduler.config.SchedulerMode` and calls ``invoker.trigger()``
when it's time. No async runtime, no in-process worker, no shared bus —
the container stays stateless.

Failure policy: every mode applies ``config.backoff_seconds`` after a
failed trigger to avoid hammering a wedged proxbox-api. ``continuous``
mode otherwise has no inter-run delay; ``interval`` mode sleeps until the
next slot regardless of last duration; ``cron`` mode sleeps until the
next cron fire time.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Callable

from .config import ModeKind, SchedulerConfig
from .cron import next_fire_time
from .invoker import InvokeResult, Invoker

logger = logging.getLogger(__name__)

Sleeper = Callable[[float], None]
Clock = Callable[[], datetime]


class SchedulerRunner:
    """Drive an :class:`Invoker` according to a :class:`SchedulerConfig`.

    The runner exposes a ``stop()`` method so tests (and signal handlers)
    can break out of the loop deterministically.
    """

    def __init__(
        self,
        *,
        config: SchedulerConfig,
        invoker: Invoker,
        sleeper: Sleeper | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._config = config
        self._invoker = invoker
        self._sleeper = sleeper or time.sleep
        self._clock = clock or (lambda: datetime.now(tz=config.timezone))
        self._stopping = False

    def stop(self) -> None:
        self._stopping = True

    def run(self) -> None:
        mode = self._config.mode
        if mode.kind is ModeKind.OFF:
            logger.info("scheduler.mode=off — exiting cleanly without scheduling work")
            return

        if mode.kind is ModeKind.CONTINUOUS:
            self._run_continuous()
            return
        if mode.kind is ModeKind.INTERVAL:
            self._run_interval()
            return
        if mode.kind is ModeKind.CRON:
            self._run_cron()
            return

        raise RuntimeError(f"Unhandled mode: {mode.kind!r}")  # pragma: no cover

    def _trigger(self) -> InvokeResult:
        logger.info("scheduler.trigger.start invoke=%s", self._config.invoke)
        result = self._invoker.trigger()
        if result.success:
            logger.info("scheduler.trigger.ok detail=%s", result.detail)
        else:
            logger.warning(
                "scheduler.trigger.fail detail=%s exit_code=%s",
                result.detail,
                result.exit_code,
            )
        return result

    def _apply_backoff_if_failed(self, result: InvokeResult) -> None:
        if not result.success and self._config.backoff_seconds > 0:
            logger.info(
                "scheduler.backoff seconds=%.1f reason=trigger_failed",
                self._config.backoff_seconds,
            )
            self._sleeper(self._config.backoff_seconds)

    def _run_continuous(self) -> None:
        logger.info("scheduler.mode=continuous starting tight loop")
        while not self._stopping:
            result = self._trigger()
            if self._stopping:
                return
            self._apply_backoff_if_failed(result)

    def _run_interval(self) -> None:
        interval = float(self._config.mode.interval_seconds or 0)
        logger.info("scheduler.mode=interval seconds=%.1f", interval)
        while not self._stopping:
            t0 = time.monotonic()
            result = self._trigger()
            if not result.success:
                self._apply_backoff_if_failed(result)
            if self._stopping:
                return
            elapsed = time.monotonic() - t0
            remaining = interval - elapsed
            if remaining > 0:
                self._sleeper(remaining)

    def _run_cron(self) -> None:
        expression = self._config.mode.cron_expression or ""
        logger.info(
            "scheduler.mode=cron expression=%r tz=%s",
            expression,
            self._config.timezone.key,
        )
        while not self._stopping:
            now = self._clock()
            next_dt = next_fire_time(expression, base=now, tz=self._config.timezone)
            wait_seconds = max(0.0, (next_dt - now).total_seconds())
            logger.info(
                "scheduler.cron.sleep next_fire=%s wait_seconds=%.1f",
                next_dt.isoformat(),
                wait_seconds,
            )
            if wait_seconds > 0:
                self._sleeper(wait_seconds)
            if self._stopping:
                return
            result = self._trigger()
            self._apply_backoff_if_failed(result)
