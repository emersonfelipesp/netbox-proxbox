"""Whole-job deadline calculations for staged synchronization."""

from __future__ import annotations

from dataclasses import dataclass
import time


class SyncJobDeadlineReached(RuntimeError):
    """Raised when no execution time remains before result persistence."""


def remaining_timeout(deadline: float | None, ceiling: float) -> float:
    """Return a positive HTTP timeout capped by an absolute monotonic deadline."""
    if deadline is None:
        return ceiling
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise SyncJobDeadlineReached("Job deadline reached.")
    return min(ceiling, remaining)


@dataclass(frozen=True)
class SyncJobDeadline:
    """A monotonic deadline that keeps a reserve for result persistence."""

    expires_at: float
    reserve_seconds: float = 120.0

    def remaining(self, now: float) -> float:
        """Return executable time remaining before the persistence reserve."""
        return max(self.expires_at - self.reserve_seconds - now, 0.0)

    def cap(self, seconds: float, now: float) -> float:
        """Cap an operation or sleep to the executable time remaining."""
        return min(max(seconds, 0.0), self.remaining(now))

    @property
    def executable_expires_at(self) -> float:
        """Return the monotonic instant at which network work must stop."""
        return self.expires_at - self.reserve_seconds

    def timeout(self, seconds: float, now: float) -> float:
        """Return a positive timeout capped by remaining execution time."""
        remaining = self.remaining(now)
        if remaining <= 0:
            raise SyncJobDeadlineReached("Job deadline reached.")
        return min(max(seconds, 0.001), remaining)
