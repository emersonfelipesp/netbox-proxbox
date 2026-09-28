"""Parse bounded HTTP Retry-After values."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math


def parse_retry_after(
    value: object,
    *,
    maximum: float,
    now: datetime | None = None,
) -> float | None:
    """Return a bounded delay for delta-seconds or an RFC 7231 HTTP-date."""
    text = str(value).strip()
    try:
        seconds = float(text)
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(text)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        reference = now or datetime.now(timezone.utc)
        seconds = (retry_at - reference).total_seconds()
    if not math.isfinite(seconds):
        return None
    return min(max(seconds, 0.0), maximum)
