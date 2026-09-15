"""Defensive parser for the Proxmox ``pve-calendar-event`` subset."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date


_MAX_SCHEDULE_LENGTH = 1024
_WEEKDAYS = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}
_ALIASES = {
    "minutely": (None, None, None, None),
    "hourly": (None, None, None, None),
    "daily": (None, None, None, None),
    "weekly": (frozenset({0}), None, None, None),
    "monthly": (None, None, None, (1, 1)),
    "yearly": (None, None, (1, 1), (1, 1)),
    "annually": (None, None, (1, 1), (1, 1)),
    "quarterly": (None, None, frozenset({1, 4, 7, 10}), (1, 1)),
    "semiannually": (None, None, frozenset({1, 7}), (1, 1)),
}
_INTEGER = re.compile(r"[0-9]+", re.ASCII)
_DATE = re.compile(r"([^\s-]+)-([^\s-]+)-([^\s-]+)", re.ASCII)
DatePart = tuple[int, int] | frozenset[int] | None


@dataclass(frozen=True, slots=True)
class ParsedSchedule:
    """Parsed date selectors plus the original time display text."""

    weekdays: frozenset[int] | None
    years: DatePart
    months: DatePart
    days: DatePart
    time_text: str
    approximate: bool
    raw: str

    def matches(self, candidate: date) -> bool:
        """Return whether ``candidate`` satisfies the parsed date selectors."""
        if self.approximate:
            return True
        return all(
            (
                self.weekdays is None or candidate.weekday() in self.weekdays,
                _part_matches(self.years, candidate.year),
                _part_matches(self.months, candidate.month),
                _part_matches(self.days, candidate.day),
            )
        )


def _part_matches(part: DatePart, value: int) -> bool:
    if part is None:
        return True
    if isinstance(part, frozenset):
        return value in part
    return part[0] <= value <= part[1]


def _unparsed(raw: str) -> ParsedSchedule:
    return ParsedSchedule(None, None, None, None, raw, True, raw)


def _weekday_range(start: int, end: int) -> set[int]:
    if start <= end:
        return set(range(start, end + 1))
    return set(range(start, 7)) | set(range(0, end + 1))


def _parse_weekdays(value: str) -> frozenset[int] | None:
    selected: set[int] = set()
    for item in value.casefold().split(","):
        if ".." not in item:
            if item not in _WEEKDAYS:
                return None
            selected.add(_WEEKDAYS[item])
            continue
        bounds = item.split("..")
        if len(bounds) != 2 or any(bound not in _WEEKDAYS for bound in bounds):
            return None
        selected.update(_weekday_range(_WEEKDAYS[bounds[0]], _WEEKDAYS[bounds[1]]))
    return frozenset(selected) if selected else None


def _parse_date_part(value: str, minimum: int, maximum: int) -> DatePart | bool:
    if value == "*":
        return None
    if ".." in value:
        bounds = value.split("..")
        if len(bounds) != 2:
            return False
        parsed = [_bounded_integer(item, minimum, maximum) for item in bounds]
        if None in parsed or parsed[0] > parsed[1]:
            return False
        return parsed[0], parsed[1]  # type: ignore[return-value]
    parsed = _bounded_integer(value, minimum, maximum)
    return (parsed, parsed) if parsed is not None else False


def _bounded_integer(value: str, minimum: int, maximum: int) -> int | None:
    if not _INTEGER.fullmatch(value):
        return None
    parsed = int(value)
    return parsed if minimum <= parsed <= maximum else None


def _parse_date(value: str) -> tuple[DatePart, DatePart, DatePart] | None:
    match = _DATE.fullmatch(value)
    if match is None:
        return None
    parts = (
        _parse_date_part(match[1], 1, 9999),
        _parse_date_part(match[2], 1, 12),
        _parse_date_part(match[3], 1, 31),
    )
    if any(part is False for part in parts):
        return None
    return parts  # type: ignore[return-value]


def _valid_time(value: str) -> bool:
    components = value.split(":")
    if not 1 <= len(components) <= 3:
        return False
    if len(components) == 1:
        maximum = 59 if value.startswith("*/") else 23
        return _valid_clock_component(value, maximum)
    return _valid_clock_component(components[0], 23) and all(
        _valid_clock_component(component, 59) for component in components[1:]
    )


def _valid_clock_component(value: str, maximum: int) -> bool:
    repetition = value.split("/")
    if len(repetition) > 2 or not _valid_repetition(repetition):
        return False
    return all(_valid_clock_atom(item, maximum) for item in repetition[0].split(","))


def _valid_repetition(parts: list[str]) -> bool:
    if len(parts) == 1:
        return True
    return bool(_INTEGER.fullmatch(parts[1])) and int(parts[1]) > 0


def _valid_clock_atom(value: str, maximum: int) -> bool:
    if value == "*":
        return True
    bounds = value.split("..")
    parsed = [_bounded_integer(item, 0, maximum) for item in bounds]
    if len(parsed) == 1:
        return parsed[0] is not None
    return len(parsed) == 2 and None not in parsed and parsed[0] <= parsed[1]


def _from_alias(alias: str, time_text: str, raw: str) -> ParsedSchedule:
    weekdays, years, months, days = _ALIASES[alias]
    return ParsedSchedule(weekdays, years, months, days, time_text, False, raw)


def _parse_tokens(tokens: list[str], raw: str) -> ParsedSchedule | None:
    first = tokens[0].casefold()
    if first in _ALIASES and len(tokens) in {1, 2}:
        time_text = first if len(tokens) == 1 else tokens[1]
        if len(tokens) == 1 or _valid_time(tokens[1]):
            return _from_alias(first, time_text, raw)
        return None
    if len(tokens) == 1 and _valid_time(tokens[0]):
        return ParsedSchedule(None, None, None, None, tokens[0], False, raw)
    return _parse_explicit_tokens(tokens, raw)


def _parse_single_token(token: str, raw: str) -> ParsedSchedule | None:
    """Handle a lone weekday or date selector, which Proxmox runs at 00:00."""
    weekdays = _parse_weekdays(token)
    if weekdays is not None:
        return ParsedSchedule(weekdays, None, None, None, "00:00", False, raw)
    parsed_date = _parse_date(token)
    if parsed_date is None:
        return None
    return ParsedSchedule(None, *parsed_date, "00:00", False, raw)


def _parse_explicit_tokens(tokens: list[str], raw: str) -> ParsedSchedule | None:
    if len(tokens) == 1:
        return _parse_single_token(tokens[0], raw)
    if len(tokens) == 2:
        weekdays = _parse_weekdays(tokens[0])
        parsed_date = _parse_date(tokens[0])
        time_text = tokens[1]
    elif len(tokens) == 3:
        weekdays = _parse_weekdays(tokens[0])
        parsed_date = _parse_date(tokens[1])
        time_text = tokens[2]
        if weekdays is None:
            return None
    else:
        return None
    if not _valid_time(time_text):
        return None
    if len(tokens) == 2 and weekdays is not None:
        return ParsedSchedule(weekdays, None, None, None, time_text, False, raw)
    if parsed_date is None:
        return None
    return ParsedSchedule(
        weekdays if len(tokens) == 3 else None, *parsed_date, time_text, False, raw
    )


def parse(schedule: str) -> ParsedSchedule:
    """Parse supported grammar, returning a fail-open schedule on any bad input."""
    try:
        raw = schedule.strip() if isinstance(schedule, str) else ""
        if not raw or len(raw) > _MAX_SCHEDULE_LENGTH:
            return _unparsed(raw)
        parsed = _parse_tokens(raw.split(), raw)
        return parsed if parsed is not None else _unparsed(raw)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return _unparsed("")
