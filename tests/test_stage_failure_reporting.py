"""Regression tests: a sync stage must not report success when nothing landed.

A Proxbox sync job used to finish ``completed`` with a green stage summary even when the
backend had rejected **every** NetBox write in that stage. Two independent defects
produced it:

1. ``sync_stages._execute_stage_sync()`` called a stage successful on any HTTP status
   below 400, and the backend's shared SSE generator sets the terminal ``complete``
   frame's ``ok`` to true whenever its sync coroutine returns without raising -- which a
   coroutine that reconciled 0 of N objects does. The per-object failures were on the
   wire (``item_progress`` frames with ``status: failed``, a terminal ``phase_summary``
   whose ``result.failed`` is non-zero, and ``error_detail`` frames) and ``on_frame()``
   logged a throttled sample of them and counted nothing.
2. The cluster/node summary counted ``ProxmoxCluster``/``ProxmoxNode`` rows in the
   plugin's own tables and read as though NetBox objects had been created.

The frame shapes below are transcribed from the backend's own builders
(``proxbox_api/schemas/stream_messages.py``) rather than derived from the consumer under
test -- a fixture read back out of the consumer would be satisfied by any consumer.
"""

from __future__ import annotations

import pytest

# ``sync_stages`` cannot be imported directly: it pulls in Django and the NetBox plugin
# framework. Reuse the established stubbed loader rather than adding a third copy of it.
from tests.test_ip_sync_mode_gate import sync_stages_module  # noqa: F401,F811


@pytest.fixture
def StageOutcome(sync_stages_module):  # noqa: N802,F811 - the fixture yields a class
    return sync_stages_module.StageOutcome


@pytest.fixture
def _as_count(sync_stages_module):  # noqa: F811
    return sync_stages_module._as_count


def _phase_summary(
    *,
    created: int = 0,
    updated: int = 0,
    deleted: int = 0,
    failed: int = 0,
    skipped: int = 0,
) -> dict[str, object]:
    """A terminal ``phase_summary`` frame, shaped as the backend builds it."""
    return {
        "phase": "devices",
        "status": "completed" if failed == 0 else "completed_with_errors",
        "message": f"Phase devices completed: {created} created, {updated} updated, {failed} failed",
        "result": {
            "created": created,
            "updated": updated,
            "deleted": deleted,
            "failed": failed,
            "skipped": skipped,
            "total": created + updated + deleted + failed + skipped,
        },
    }


def _item_progress(
    *, status: str, operation: str, error: str | None = None
) -> dict[str, object]:
    frame: dict[str, object] = {
        "phase": "devices",
        "item": {"name": "pve01", "type": "node"},
        "operation": operation,
        "status": status,
        "message": f"device pve01 {status}",
    }
    if error is not None:
        frame["error"] = error
    return frame


# --------------------------------------------------------------------------------------
# Verdict
# --------------------------------------------------------------------------------------


def test_clean_stage_is_success(StageOutcome) -> None:
    outcome = StageOutcome()
    outcome.observe("phase_summary", _phase_summary(created=3))
    assert outcome.status() == "success"
    assert outcome.failed == 0
    assert outcome.succeeded == 3


def test_stage_where_nothing_landed_is_failed(StageOutcome) -> None:
    """The reported case: NetBox rejected every write, the stream still returned 200."""
    outcome = StageOutcome()
    outcome.observe("phase_summary", _phase_summary(created=0, failed=2))
    assert outcome.status() == "failed"
    assert outcome.failed == 2
    assert outcome.succeeded == 0


def test_partially_failed_stage_is_a_warning_not_a_failure(StageOutcome) -> None:
    """One unreachable guest must not error an estate-wide scheduled sync."""
    outcome = StageOutcome()
    outcome.observe("phase_summary", _phase_summary(created=5, failed=1))
    assert outcome.status() == "warning"


def test_updates_and_deletes_count_as_successes(StageOutcome) -> None:
    """A stage that only updates existing objects has landed work."""
    outcome = StageOutcome()
    outcome.observe("phase_summary", _phase_summary(updated=2, deleted=1, failed=1))
    assert outcome.status() == "warning"
    assert outcome.succeeded == 3


def test_skipped_objects_are_not_counted_as_successes(StageOutcome) -> None:
    """A stage that skipped everything and failed the rest landed nothing."""
    outcome = StageOutcome()
    outcome.observe("phase_summary", _phase_summary(skipped=4, failed=1))
    assert outcome.status() == "failed"


# --------------------------------------------------------------------------------------
# Evidence precedence
# --------------------------------------------------------------------------------------


def test_item_progress_is_counted_when_no_phase_summary_arrives(StageOutcome) -> None:
    """Stages that predate the summary frame must still report."""
    outcome = StageOutcome()
    outcome.observe(
        "item_progress",
        _item_progress(status="failed", operation="failed", error="rejected"),
    )
    outcome.observe(
        "item_progress", _item_progress(status="completed", operation="created")
    )
    assert outcome.failed == 1
    assert outcome.succeeded == 1
    assert outcome.status() == "warning"


def test_phase_summary_wins_over_item_progress_rather_than_adding_to_it(
    StageOutcome,
) -> None:
    """A stage emitting both must not have its failures counted twice."""
    outcome = StageOutcome()
    for _ in range(3):
        outcome.observe(
            "item_progress", _item_progress(status="failed", operation="failed")
        )
    outcome.observe("phase_summary", _phase_summary(created=0, failed=3))
    assert outcome.failed == 3, "double-counting would report 6"


def test_error_detail_counts_only_when_nothing_else_reported(StageOutcome) -> None:
    outcome = StageOutcome()
    outcome.observe("error_detail", {"message": "boom", "category": "internal"})
    assert outcome.failed == 1
    # ...but it cannot be `failed`: see the next test.
    assert outcome.status() == "warning"

    with_summary = StageOutcome()
    with_summary.observe("error_detail", {"message": "boom", "category": "internal"})
    with_summary.observe("phase_summary", _phase_summary(created=2))
    assert with_summary.failed == 0, (
        "an error already reflected in the tally is not extra"
    )
    assert with_summary.status() == "success"


def test_operation_failed_is_detected_even_when_status_is_not(StageOutcome) -> None:
    outcome = StageOutcome()
    outcome.observe(
        "item_progress", _item_progress(status="processing", operation="failed")
    )
    assert outcome.failed == 1


# --------------------------------------------------------------------------------------
# Hostile frames -- this reads data produced outside the repository
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "frame",
    [
        {},
        {"result": None},
        {"result": "not-a-dict"},
        {"result": []},
        {"result": {"failed": "3", "created": "1"}},
        {"result": {"failed": None, "created": None}},
        {"result": {"failed": -5}},
        {"result": {"failed": True}},
        {"result": {"failed": 2.9}},
        {"result": {"failed": {"nested": 1}}},
    ],
)
def test_malformed_phase_summary_never_raises(frame: dict, StageOutcome) -> None:
    """A frame the backend could plausibly change shape on must not kill the sync."""
    outcome = StageOutcome()
    outcome.observe("phase_summary", frame)
    assert outcome.failed >= 0
    assert outcome.status() in {"success", "warning", "failed"}


@pytest.mark.parametrize(
    "frame",
    [
        {},
        {"status": None},
        {"operation": 42},
        {"status": ["failed"]},
        {"error": {"a": 1}},
    ],
)
def test_malformed_item_progress_never_raises(frame: dict, StageOutcome) -> None:
    outcome = StageOutcome()
    outcome.observe("item_progress", frame)
    assert outcome.status() in {"success", "warning", "failed"}


def test_unknown_event_types_are_ignored(StageOutcome) -> None:
    outcome = StageOutcome()
    for event in (
        "step",
        "discovery",
        "substep",
        "complete",
        "duplicate_name_resolved",
        "",
    ):
        outcome.observe(event, {"anything": "at all"})
    assert outcome.status() == "success"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (3, 3),
        ("3", 3),
        (" 3 ", 3),
        (3.9, 3),
        (-2, 0),
        (None, 0),
        (True, 0),
        (False, 0),
        ("abc", 0),
        ([], 0),
        ({}, 0),
    ],
)
def test_as_count_coerces_external_values_without_raising(
    value: object, expected: int, _as_count
) -> None:
    """``True`` must not become 1: a boolean in a counter field is a shape error."""
    assert _as_count(value) == expected


# --------------------------------------------------------------------------------------
# Persisted record and operator-facing text
# --------------------------------------------------------------------------------------


def test_result_summary_keys_are_additive_and_typed(StageOutcome) -> None:
    outcome = StageOutcome()
    outcome.observe("phase_summary", _phase_summary(created=1, failed=2))
    summary = outcome.as_result_summary()
    assert summary["status"] == "warning"
    assert summary["failed"] == 2
    assert summary["succeeded"] == 1
    assert isinstance(summary["errors"], list)


def test_error_samples_are_bounded_and_deduplicated(StageOutcome) -> None:
    """The samples land in a long-lived job record; they cannot grow with the estate."""
    outcome = StageOutcome()
    for index in range(50):
        outcome.observe(
            "item_progress",
            _item_progress(status="failed", operation="failed", error=f"error {index}"),
        )
    for _ in range(10):
        outcome.observe(
            "item_progress",
            _item_progress(status="failed", operation="failed", error="error 0"),
        )
    samples = outcome.as_result_summary()["errors"]
    assert len(samples) <= 3
    assert len(set(samples)) == len(samples)
    # The count is not sampled away -- every failure is still tallied.
    assert outcome.failed == 60


def test_a_clean_stage_records_no_error_samples(StageOutcome) -> None:
    outcome = StageOutcome()
    outcome.observe("phase_summary", _phase_summary(created=2))
    assert "errors" not in outcome.as_result_summary()


def test_counters_do_not_leak_between_stage_instances(StageOutcome) -> None:
    """Each stage and stream path gets a fresh accumulator; nothing may carry over."""
    first = StageOutcome()
    first.observe("phase_summary", _phase_summary(created=0, failed=4))
    second = StageOutcome()
    second.observe("phase_summary", _phase_summary(created=4))
    assert first.status() == "failed"
    assert second.status() == "success"
    assert second.failed == 0


def test_error_detail_alone_cannot_declare_that_nothing_landed(StageOutcome) -> None:
    """An error frame carries no denominator, so "nothing landed" is not derivable.

    Several backend paths emit ``error_detail`` for a condition that does not abort the
    stage. Treating one as proof that the stage synced nothing would error runs that
    actually synced -- replacing a false green with a false red.
    """
    outcome = StageOutcome()
    for index in range(5):
        outcome.observe(
            "error_detail", {"message": f"boom {index}", "category": "internal"}
        )
    assert outcome.failed == 5
    assert outcome.status() == "warning"


def test_a_denominator_from_item_frames_does_allow_a_failed_verdict(
    StageOutcome,
) -> None:
    """With per-object frames the denominator is known, so `failed` is derivable."""
    outcome = StageOutcome()
    outcome.observe(
        "item_progress", _item_progress(status="failed", operation="failed")
    )
    assert outcome.status() == "failed"


def test_retry_reset_discards_a_failed_attempt(StageOutcome) -> None:
    """``_execute_stage_sync`` retries, and every attempt replays its own frames.

    Without the reset, an attempt that failed and then succeeded on retry would still
    be reported as failed, with both attempts' counts summed.
    """
    outcome = StageOutcome()
    outcome.observe("phase_summary", _phase_summary(created=0, failed=4))
    assert outcome.status() == "failed"

    outcome.reset()
    outcome.observe("phase_summary", _phase_summary(created=4, failed=0))
    assert outcome.status() == "success"
    assert outcome.failed == 0
    assert outcome.succeeded == 4, (
        "the failed attempt's counts must not be carried over"
    )
    assert "errors" not in outcome.as_result_summary(), (
        "error samples from the discarded attempt must be gone too"
    )
