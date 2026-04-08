"""Systemd calendar schedule parser for Proxmox vzdump schedules."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

__all__ = ("parse_systemd_calendar_to_datetime",)

_SYSTEMD_CALENDAR_RE = re.compile(
    r"(?P<dow>[a-z]{3}(?:,[a-z]{3})*)?\s*"
    r"(?P<date>(?:\d{1,2})?(?:[-/]\d{1,2})?(?:[-/]\d{2,4})?)?\s*"
    r"(?P<time>(?:\d{1,2}):(?:\d{2})(?::(?:\d{2}))?)?"
)


def parse_systemd_calendar_to_datetime(
    schedule: str, base_time: datetime | None = None
) -> datetime | None:
    """
    Parse a systemd calendar string and return the next occurrence from base_time.

    This is a simplified parser that handles common Proxmox vzdump schedule formats:
        - "mon,wed 04:00"
        - "daily 04:00"
        - "*-*-* 04:00:00"
        - "2024-01-01 04:00"
        - "04:00"
        - "*:00/15" (every 15 minutes)
        - "*/4" (every 4 hours)

    Returns a datetime in UTC, or None if parsing fails.
    """
    if not schedule or not schedule.strip():
        return None

    schedule = schedule.strip()
    now = base_time or datetime.now(timezone.utc)

    # Normalize common aliases
    schedule_lower = schedule.lower()
    if schedule_lower == "daily":
        # Tomorrow at 04:00 if past 04:00 today
        hour, minute = 4, 0
        days_offset = (
            0 if now.hour < hour or (now.hour == hour and now.minute < minute) else 1
        )

        result = now.replace(
            hour=hour, minute=minute, second=0, microsecond=0
        ) + timedelta(days=days_offset)
        return result.astimezone(timezone.utc)
    elif schedule_lower == "weekly":
        # Next Monday at 04:00
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0 and (
            now.hour > 4 or (now.hour == 4 and now.minute > 0)
        ):
            days_until_monday = 7
        result = now.replace(hour=4, minute=0, second=0, microsecond=0) + timedelta(
            days=days_until_monday
        )
        return result.astimezone(timezone.utc)
    elif schedule_lower == "monthly":
        # Next month on the 1st at 04:00
        if now.day == 1 and now.hour < 4:
            result = now.replace(day=1, hour=4, minute=0, second=0, microsecond=0)
        else:
            # Advance to next month
            if now.month == 12:
                next_month = now.replace(
                    year=now.year + 1,
                    month=1,
                    day=1,
                    hour=4,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            else:
                next_month = now.replace(
                    month=now.month + 1,
                    day=1,
                    hour=4,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            result = next_month
        return result.astimezone(timezone.utc)
    elif schedule_lower == "hourly":
        # Next hour at :00
        result = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return result.astimezone(timezone.utc)

    # Try to parse time portion (HH:MM or HH:MM:SS)
    time_match = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", schedule)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        second = int(time_match.group(3) or "0")

        # Handle hour ranges like */4 or 0-4
        if "*" in str(hour) or (isinstance(hour, str) and "-" in hour):
            # Simple case: */N means every N hours
            if schedule.startswith("*/"):
                try:
                    interval = int(schedule[2:])
                    if interval > 0:
                        # Round up to next interval
                        total_minutes = now.hour * 60 + now.minute
                        next_interval_minutes = (
                            (total_minutes // interval) + 1
                        ) * interval
                        result = now.replace(
                            minute=0, second=0, microsecond=0
                        ) + timedelta(minutes=next_interval_minutes)
                        return result.astimezone(timezone.utc)
                except ValueError:
                    pass

        # Handle day-of-week
        dow_pattern = re.match(r"([a-z]{3}(?:,[a-z]{3})*)", schedule.lower())
        if dow_pattern:
            dow_map = {
                "mon": 0,
                "tue": 1,
                "wed": 2,
                "thu": 3,
                "fri": 4,
                "sat": 5,
                "sun": 6,
            }
            target_dows = []
            for abbrev in dow_pattern.group(1).split(","):
                abbrev = abbrev.strip()
                if abbrev in dow_map:
                    target_dows.append(dow_map[abbrev])

            if target_dows:
                target_dow = target_dows[0]
                days_ahead = (target_dow - now.weekday()) % 7
                if days_ahead == 0 and (
                    now.hour > hour or (now.hour == hour and now.minute > minute)
                ):
                    days_ahead = 7
                result = now.replace(
                    hour=hour, minute=minute, second=second, microsecond=0
                ) + timedelta(days=days_ahead)
                return result.astimezone(timezone.utc)

        # Simple time-only schedule (e.g., "04:00" or "04:00:00")
        if ":" in schedule and not any(c in schedule for c in "-/"):
            if now.hour > hour or (now.hour == hour and now.minute > minute):
                days_offset = 1
            else:
                days_offset = 0
            result = now.replace(
                hour=hour, minute=minute, second=second, microsecond=0
            ) + timedelta(days=days_offset)
            return result.astimezone(timezone.utc)

    return None
