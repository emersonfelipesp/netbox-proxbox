"""Pure calendar layout helpers for Proxbox data-protection views."""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Mapping, Sequence, TypeVar
from urllib.parse import urlencode


CALENDAR_EVENT_LIMIT = 4
CALENDAR_OVERFLOW_LIMIT = 40
CALENDAR_SOURCE_LIMIT = 1000

RowT = TypeVar("RowT")


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    """One dated item rendered in a data-protection calendar cell."""

    day: date
    kind: str
    label: str
    url: str
    time_text: str
    muted: bool
    approximate: bool
    sort_key: str


@dataclass(frozen=True, slots=True)
class CalendarDayCell:
    """One calendar day and its capped and overflow event collections."""

    date: date
    in_month: bool
    is_today: bool
    events: tuple[CalendarEvent, ...]
    overflow: tuple[CalendarEvent, ...]
    hidden_count: int

    @property
    def visible_events(self) -> tuple[CalendarEvent, ...]:
        """Return the events shown before the overflow expander."""
        return self.events

    @property
    def additional_count(self) -> int:
        """Return every event represented by the overflow expander."""
        return len(self.overflow) + self.hidden_count


def _month_grid_dates(anchor: date) -> list[list[date]]:
    return calendar.Calendar(firstweekday=calendar.MONDAY).monthdatescalendar(
        anchor.year, anchor.month
    )


def visible_range(anchor: date, view: str) -> tuple[date, date]:
    """Return the inclusive start and exclusive end dates rendered by a view."""
    if view == "week":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=7)
    rows = _month_grid_dates(anchor)
    return rows[0][0], rows[-1][-1] + timedelta(days=1)


def _shift_month(anchor: date, delta: int) -> date:
    month_index = anchor.year * 12 + anchor.month - 1 + delta
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(anchor.day, last_day))


def shift_anchor(anchor: date, view: str, delta: int) -> date:
    """Shift an anchor by calendar months or ISO weeks."""
    if view == "week":
        return anchor + timedelta(weeks=delta)
    return _shift_month(anchor, delta)


def cap_day_events(
    events: Iterable[CalendarEvent],
    limit: int = CALENDAR_EVENT_LIMIT,
    overflow_limit: int = CALENDAR_OVERFLOW_LIMIT,
) -> tuple[tuple[CalendarEvent, ...], tuple[CalendarEvent, ...], int]:
    """Split sorted events into visible, bounded overflow, and hidden counts."""
    ordered = tuple(sorted(events, key=lambda event: event.sort_key))
    cap = max(0, limit)
    overflow_cap = max(0, overflow_limit)
    overflow_end = cap + overflow_cap
    return ordered[:cap], ordered[cap:overflow_end], max(0, len(ordered) - overflow_end)


@dataclass(frozen=True, slots=True)
class SourceTruncation:
    """What a bounded source left out, in units the notice can name honestly.

    ``omitted_events`` counts projected occurrences dropped from objects that
    were inspected, so it is exact. ``unprojected_objects`` counts scheduled
    objects that were fetched but never projected once the event budget was
    spent, also exact. ``more_rows`` records that the source held more rows
    than the fetch limit; the remainder is deliberately not counted, because an
    exact ``COUNT`` over a large permission-filtered source costs more than the
    bounded render it would describe.
    """

    omitted_events: int = 0
    unprojected_objects: int = 0
    more_rows: bool = False

    def __bool__(self) -> bool:
        """True when anything was left out of the rendered calendar."""
        return bool(self.omitted_events or self.unprojected_objects or self.more_rows)

    def merge(self, other: SourceTruncation) -> SourceTruncation:
        """Combine two sources' truncation into one page-level summary."""
        return SourceTruncation(
            omitted_events=self.omitted_events + other.omitted_events,
            unprojected_objects=self.unprojected_objects + other.unprojected_objects,
            more_rows=self.more_rows or other.more_rows,
        )


def materialize_source_rows(
    rows: Sequence[RowT], limit: int = CALENDAR_SOURCE_LIMIT
) -> tuple[list[RowT], bool]:
    """Fetch at most ``limit`` rows and report whether any were left behind.

    Fetching ``limit + 1`` rows answers "is there more?" with the same bounded
    query instead of a separate full-source ``COUNT``.
    """
    cap = max(0, limit)
    materialized = list(rows[: cap + 1])
    return materialized[:cap], len(materialized) > cap


def _events_by_day(
    events: Iterable[CalendarEvent],
) -> Mapping[date, list[CalendarEvent]]:
    grouped: dict[date, list[CalendarEvent]] = defaultdict(list)
    for event in events:
        grouped[event.day].append(event)
    return grouped


def _day_cell(
    day: date,
    anchor: date,
    grouped: Mapping[date, Sequence[CalendarEvent]],
    today: date,
) -> CalendarDayCell:
    visible, overflow, hidden_count = cap_day_events(grouped.get(day, ()))
    return CalendarDayCell(
        date=day,
        in_month=day.month == anchor.month,
        is_today=day == today,
        events=visible,
        overflow=overflow,
        hidden_count=hidden_count,
    )


def build_month_grid(
    anchor: date, events: Iterable[CalendarEvent], today: date | None = None
) -> list[list[CalendarDayCell]]:
    """Build Monday-first rows for the month containing ``anchor``.

    ``today`` marks the highlighted cell; callers inside Django pass the
    configured local date so the marker follows ``TIME_ZONE`` rather than the
    host clock.
    """
    grouped = _events_by_day(events)
    current = today or date.today()
    return [
        [_day_cell(day, anchor, grouped, current) for day in week]
        for week in _month_grid_dates(anchor)
    ]


def build_week_grid(
    anchor: date, events: Iterable[CalendarEvent], today: date | None = None
) -> list[list[CalendarDayCell]]:
    """Build one Monday-first ISO week containing ``anchor``."""
    start, _ = visible_range(anchor, "week")
    grouped = _events_by_day(events)
    current = today or date.today()
    return [
        [
            _day_cell(start + timedelta(days=offset), anchor, grouped, current)
            for offset in range(7)
        ]
    ]


def _query_items(params: object) -> list[tuple[str, str]]:
    lists = getattr(params, "lists", None)
    if callable(lists):
        return [(str(key), str(value)) for key, values in lists() for value in values]
    items = getattr(params, "items", None)
    if callable(items):
        return [(str(key), str(value)) for key, value in items()]
    return [(str(key), str(value)) for key, value in params]  # type: ignore[union-attr]


def calendar_query_string(params: object, view: str, anchor: date) -> str:
    """Replace calendar state while preserving every other query parameter."""
    kept = [
        (key, value)
        for key, value in _query_items(params)
        if key not in {"cal_view", "cal_date"}
    ]
    kept.extend(
        (value for value in (("cal_view", view), ("cal_date", anchor.isoformat())))
    )
    return urlencode(kept, doseq=True)
