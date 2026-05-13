"""Container entrypoint: ``python -m proxbox_scheduler``.

Parses the environment, configures logging, builds the invoker, and runs
the scheduler loop until SIGTERM/SIGINT.
"""

from __future__ import annotations

import logging
import signal
import sys

from .config import ConfigError, load_config
from .invoker import build_invoker
from .logging_config import configure_logging
from .runner import SchedulerRunner

logger = logging.getLogger("proxbox_scheduler")


def main(argv: list[str] | None = None) -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        sys.stderr.write(f"proxbox-scheduler: configuration error: {exc}\n")
        return 2

    configure_logging(level=config.log_level, json_output=config.log_json)
    logger.info(
        "scheduler.start mode=%s invoke=%s tz=%s",
        config.mode.kind.value,
        config.invoke,
        config.timezone.key,
    )

    invoker = build_invoker(config)
    runner = SchedulerRunner(config=config, invoker=invoker)

    def _handle_signal(signum: int, _frame: object) -> None:
        logger.info("scheduler.signal received=%s — shutting down", signum)
        runner.stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handle_signal)
        except ValueError:
            # Happens when called from a non-main thread (e.g. tests).
            pass

    try:
        runner.run()
    except Exception:  # noqa: BLE001
        logger.exception("scheduler.crash")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
