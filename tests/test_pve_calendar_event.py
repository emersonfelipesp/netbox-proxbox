"""Pure behavior tests for the defensive Proxmox schedule parser."""

from __future__ import annotations

import importlib.util
import random
import string
import sys
from datetime import date
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "netbox_proxbox"
    / "services"
    / "pve_calendar_event.py"
)
SPEC = importlib.util.spec_from_file_location("pve_calendar_event_test", MODULE_PATH)
assert SPEC and SPEC.loader
schedule_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = schedule_module
SPEC.loader.exec_module(schedule_module)
parse = schedule_module.parse


def test_weekday_lists_and_ranges_are_case_insensitive() -> None:
    monday = date(2026, 9, 14)
    saturday = date(2026, 9, 19)

    weekdays = parse("MON,TUE 03:00")
    workweek = parse("mon..fri 03:00")
    weekend = parse("sat,sun 03:00")

    assert weekdays.matches(monday)
    assert not weekdays.matches(saturday)
    assert workweek.matches(monday)
    assert not workweek.matches(saturday)
    assert weekend.matches(saturday)
    assert not weekend.matches(monday)


def test_date_parts_match_wildcards_exact_values_and_ranges() -> None:
    first = parse("*-*-01 03:00")
    september = parse("2026-09-* */15")
    first_half = parse("*-*-1..15 *:00/15")

    assert first.matches(date(2026, 9, 1))
    assert not first.matches(date(2026, 9, 2))
    assert september.matches(date(2026, 9, 30))
    assert not september.matches(date(2026, 10, 1))
    assert first_half.matches(date(2026, 9, 15))
    assert not first_half.matches(date(2026, 9, 16))


def test_supported_time_specifications_are_preserved_for_display() -> None:
    for value in (
        "22",
        "1,2,3",
        "1..3",
        "8..17:00/30",
        "*/2:00",
        "*/5",
        "03:00:30",
        "1,5:30",
        "*:0/15",
    ):
        parsed = parse(value)
        assert not parsed.approximate
        assert parsed.time_text == value


def test_proxmox_admin_guide_calendar_event_conformance_corpus() -> None:
    # Proxmox VE Administration Guide, "Calendar Events", especially the
    # format and examples sections:
    # https://pve.proxmox.com/pve-docs/pve-admin-guide.html#chapter_calendar_events
    week = [date(2026, 9, 14 + offset) for offset in range(7)]
    corpus = {
        "mon,tue,wed,thu,fri 21:00": {0, 1, 2, 3, 4},
        "sat 18:15": {5},
        "mon..fri 22": {0, 1, 2, 3, 4},
        "*/5": set(range(7)),
        "8:00/15": set(range(7)),
        "*-*-14..18 06:00": {0, 1, 2, 3, 4},
    }

    for expression, expected_weekdays in corpus.items():
        parsed = parse(expression)
        projected = {day.weekday() for day in week if parsed.matches(day)}
        assert parsed.approximate is False, expression
        assert projected == expected_weekdays, expression


def test_aliases_apply_their_calendar_day_semantics() -> None:
    monday = date(2026, 9, 14)
    tuesday = date(2026, 9, 15)

    assert parse("minutely").matches(tuesday)
    assert parse("hourly").matches(tuesday)
    assert parse("daily").matches(tuesday)
    assert parse("weekly").matches(monday)
    assert not parse("weekly").matches(tuesday)
    assert parse("monthly").matches(date(2026, 9, 1))
    assert not parse("monthly").matches(date(2026, 9, 2))
    assert parse("yearly").matches(date(2026, 1, 1))
    assert parse("annually").matches(date(2026, 1, 1))
    assert parse("quarterly").matches(date(2026, 4, 1))
    assert parse("semiannually").matches(date(2026, 7, 1))


def test_alias_with_explicit_time_is_supported() -> None:
    parsed = parse("daily 04:00")

    assert not parsed.approximate
    assert parsed.time_text == "04:00"
    assert parsed.matches(date(2026, 9, 14))


def test_unparseable_values_fail_open_and_keep_the_raw_text() -> None:
    for raw in ("", "   ", "garbage", "mon ((( 03:00", "☃ nested[odd]{value}"):
        parsed = parse(raw)
        assert parsed.approximate
        assert parsed.matches(date(2026, 9, 14))
        assert parsed.raw == raw.strip()


def test_none_and_very_long_input_never_raise() -> None:
    none_value = parse(None)  # type: ignore[arg-type]
    long_value = parse("x" * 10_000)

    assert none_value.approximate and none_value.matches(date.today())
    assert long_value.approximate and long_value.matches(date.today())


def test_hostile_input_fuzz_never_raises_and_always_returns_a_matcher() -> None:
    randomizer = random.Random(534)
    alphabet = string.printable + "☃é中\x00[]{}()"

    for _ in range(500):
        raw = "".join(
            randomizer.choice(alphabet) for _ in range(randomizer.randrange(300))
        )
        parsed = parse(raw)
        assert isinstance(parsed.matches(date(2026, 9, 14)), bool)


def test_lone_weekday_or_date_selector_runs_at_midnight() -> None:
    monday = date(2026, 9, 14)
    first = date(2026, 10, 1)

    weekday_only = parse("mon")
    weekend_only = parse("sat,sun")
    date_only = parse("*-*-01")
    exact_date = parse("2026-09-14")

    assert not weekday_only.approximate
    assert weekday_only.time_text == "00:00"
    assert weekday_only.matches(monday)
    assert not weekday_only.matches(first)
    assert weekend_only.matches(date(2026, 9, 19))
    assert not weekend_only.matches(monday)
    assert date_only.matches(first)
    assert not date_only.matches(monday)
    assert exact_date.matches(monday)
    assert not exact_date.matches(date(2026, 9, 15))
