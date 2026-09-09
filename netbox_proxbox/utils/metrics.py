"""Shared bounded time validators for the Proxmox metrics query surfaces."""

from __future__ import annotations

import re
from datetime import datetime

_DURATION_PATTERN = re.compile(r"^-?(?:\d+(?:ns|us|µs|ms|s|m|h|d|w|mo|y))+$")
_POSITIVE_DURATION_PATTERN = re.compile(
    r"^\d+(?:ns|us|µs|ms|s|m|h|d|w|mo|y)(?:\d+(?:ns|us|µs|ms|s|m|h|d|w|mo|y))*$"
)


def validate_metrics_time(value: str, *, allow_now: bool = False) -> str:
    """Validate an Influx duration or timezone-qualified RFC3339 timestamp."""
    value = value.strip()
    if allow_now and value == "now()":
        return value
    if _DURATION_PATTERN.fullmatch(value):
        return value
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Use an Influx duration or RFC3339 timestamp.") from exc
    if parsed.tzinfo is None:
        raise ValueError("RFC3339 timestamps must include a timezone.")
    return value


def validate_metrics_interval(value: str) -> str:
    """Validate a positive Influx aggregate-window duration."""
    value = value.strip()
    if not _POSITIVE_DURATION_PATTERN.fullmatch(value):
        raise ValueError("Use a positive Influx aggregation duration.")
    return value
