"""Pure tests for data-protection calendar grids and navigation."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "netbox_proxbox"
    / "services"
    / "data_protection_calendar.py"
)
SPEC = importlib.util.spec_from_file_location(
    "data_protection_calendar_test", MODULE_PATH
)
assert SPEC and SPEC.loader
calendar_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = calendar_module
SPEC.loader.exec_module(calendar_module)

CalendarEvent = calendar_module.CalendarEvent
CALENDAR_OVERFLOW_LIMIT = calendar_module.CALENDAR_OVERFLOW_LIMIT
CALENDAR_SOURCE_LIMIT = calendar_module.CALENDAR_SOURCE_LIMIT
build_month_grid = calendar_module.build_month_grid
build_week_grid = calendar_module.build_week_grid
calendar_query_string = calendar_module.calendar_query_string
cap_day_events = calendar_module.cap_day_events
materialize_source_rows = calendar_module.materialize_source_rows
SourceTruncation = calendar_module.SourceTruncation
shift_anchor = calendar_module.shift_anchor
visible_range = calendar_module.visible_range


def _event(day: date, index: int = 0) -> CalendarEvent:
    return CalendarEvent(
        day=day,
        kind="backup",
        label=f"Backup {index}",
        url=f"/backups/{index}/",
        time_text=f"0{index}:00",
        muted=False,
        approximate=False,
        sort_key=f"{index:02d}",
    )


def test_leap_february_month_grid_covers_the_complete_month() -> None:
    rows = build_month_grid(date(2024, 2, 15), [_event(date(2024, 2, 29))])

    assert rows[0][0].date == date(2024, 1, 29)
    assert rows[-1][-1].date == date(2024, 3, 3)
    leap_day = next(
        cell for row in rows for cell in row if cell.date == date(2024, 2, 29)
    )
    assert leap_day.date == date(2024, 2, 29)
    assert leap_day.events[0].label == "Backup 0"


def test_month_starting_on_sunday_is_monday_first() -> None:
    rows = build_month_grid(date(2023, 10, 1), [])

    assert rows[0][0].date == date(2023, 9, 25)
    assert rows[0][-1].date == date(2023, 10, 1)


def test_week_grid_spans_a_month_boundary() -> None:
    rows = build_week_grid(date(2026, 9, 1), [])

    assert [cell.date for cell in rows[0]] == [
        date(2026, 8, 31),
        date(2026, 9, 1),
        date(2026, 9, 2),
        date(2026, 9, 3),
        date(2026, 9, 4),
        date(2026, 9, 5),
        date(2026, 9, 6),
    ]


def test_per_day_cap_bounds_overflow_and_counts_further_hidden_events() -> None:
    event_count = 4 + CALENDAR_OVERFLOW_LIMIT + 6
    events = [_event(date(2026, 9, 14), index) for index in range(event_count)]

    visible, overflow, hidden_count = cap_day_events(reversed(events))

    assert len(visible) == 4
    assert len(overflow) == CALENDAR_OVERFLOW_LIMIT
    assert hidden_count == 6

    cell = next(
        cell
        for row in build_month_grid(date(2026, 9, 14), events)
        for cell in row
        if cell.date == date(2026, 9, 14)
    )
    assert cell.overflow == overflow
    assert cell.hidden_count == 6
    assert cell.additional_count == CALENDAR_OVERFLOW_LIMIT + 6


class _FakeRows:
    def __init__(self, values: list[int]) -> None:
        self.values = values
        self.count_calls = 0
        self.slices: list[slice] = []

    def __getitem__(self, item: slice) -> list[int]:
        self.slices.append(item)
        return self.values[item]

    def count(self) -> int:
        self.count_calls += 1
        return len(self.values)


def test_source_materialization_caps_rows_and_flags_more_without_counting() -> None:
    source = _FakeRows(list(range(CALENDAR_SOURCE_LIMIT + 7)))

    rows, more_rows = materialize_source_rows(source, CALENDAR_SOURCE_LIMIT)

    assert len(rows) == CALENDAR_SOURCE_LIMIT
    assert more_rows is True
    assert source.count_calls == 0
    assert source.slices == [slice(None, CALENDAR_SOURCE_LIMIT + 1)]


def test_source_materialization_below_the_limit_reports_nothing_more() -> None:
    source = _FakeRows([1, 2])

    rows, more_rows = materialize_source_rows(source, 3)

    assert rows == [1, 2]
    assert more_rows is False
    assert source.count_calls == 0


def test_source_materialization_exactly_at_the_limit_is_not_truncated() -> None:
    source = _FakeRows([1, 2, 3])

    rows, more_rows = materialize_source_rows(source, 3)

    assert rows == [1, 2, 3]
    assert more_rows is False


def test_source_truncation_merges_and_is_falsy_when_nothing_was_left_out() -> None:
    empty = SourceTruncation()
    partial = SourceTruncation(omitted_events=3, unprojected_objects=2)
    more = SourceTruncation(more_rows=True)

    assert not empty
    assert partial
    merged = empty.merge(partial).merge(more)
    assert merged == SourceTruncation(3, 2, True)


def test_month_and_week_visible_ranges_cover_rendered_cells() -> None:
    assert visible_range(date(2024, 2, 15), "month") == (
        date(2024, 1, 29),
        date(2024, 3, 4),
    )
    assert visible_range(date(2026, 9, 1), "week") == (
        date(2026, 8, 31),
        date(2026, 9, 7),
    )


def test_anchor_shifts_across_year_boundaries_and_clamps_days() -> None:
    assert shift_anchor(date(2026, 1, 15), "month", -1) == date(2025, 12, 15)
    assert shift_anchor(date(2026, 12, 15), "month", 1) == date(2027, 1, 15)
    assert shift_anchor(date(2024, 1, 31), "month", 1) == date(2024, 2, 29)
    assert shift_anchor(date(2026, 1, 1), "week", -1) == date(2025, 12, 25)


def test_query_string_preserves_filters_ordering_duplicates_and_page_size() -> None:
    params = [
        ("status", "active"),
        ("status", "stale"),
        ("ordering", "-created"),
        ("per_page", "100"),
        ("cal_view", "month"),
        ("cal_date", "2025-01-01"),
    ]

    query = calendar_query_string(params, "week", date(2026, 9, 14))

    assert query == (
        "status=active&status=stale&ordering=-created&per_page=100"
        "&cal_view=week&cal_date=2026-09-14"
    )


def test_undated_count_is_an_explicit_calendar_context_contract() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "netbox_proxbox"
        / "views"
        / "data_protection.py"
    ).read_text(encoding="utf-8")

    assert "undated_count" in source
    assert '__isnull": True' in source


def test_today_marker_follows_the_caller_supplied_date() -> None:
    anchor = date(2026, 9, 14)
    explicit_today = date(2026, 9, 20)

    month_rows = build_month_grid(anchor, [], today=explicit_today)
    week_rows = build_week_grid(anchor, [], today=explicit_today)

    month_today = [cell.date for row in month_rows for cell in row if cell.is_today]
    week_today = [cell.date for row in week_rows for cell in row if cell.is_today]
    assert month_today == [explicit_today]
    assert week_today == [explicit_today]

    far_away = date(1999, 1, 1)
    assert not any(
        cell.is_today for row in build_month_grid(far_away, []) for cell in row
    )
