"""Real-database parity between ``proxbox_sync_job_q`` and ``is_proxbox_sync_job``.

The Proxbox-only jobs page filters in SQL; every other consumer of "is this a
Proxbox job?" asks the Python predicate one row at a time. Two implementations
of one rule drift, and the drift is invisible: a ``Q`` that is too narrow makes
sync jobs vanish from the page operators use to find failures, and one that is
too wide leaks other plugins' jobs into it.

So this does not assert that the ``Q`` matches a hand-written list of expected
rows -- that would only check the ``Q`` against my transcription of it. It
builds a matrix of ``Job`` rows, asks the **predicate** which ones are Proxbox
jobs, asks the **database** the same question through the ``Q``, and requires
the two answers to be equal. The predicate is the oracle; the ``Q`` is what is
under test.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import uuid

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOTS = (
    REPO_ROOT.parent / "netbox" / "netbox",
    REPO_ROOT.parents[1] / "nmulticloud-context" / "netbox" / "netbox",
)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_REQUIRE_DJANGO = os.environ.get("NETBOX_PROXBOX_REQUIRE_DJANGO", "").lower() in (
    "1",
    "true",
    "yes",
)

try:
    import django
except ModuleNotFoundError:
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        "Django/NetBox test dependencies are not installed in this environment.",
        allow_module_level=True,
    )

if not hasattr(django, "__path__"):
    pytest.skip(
        "The mocked suite does not provide a real Django package.",
        allow_module_level=True,
    )

for candidate_path in NETBOX_ROOTS:
    candidate_string = str(candidate_path)
    if candidate_path.exists() and candidate_string not in sys.path:
        sys.path.insert(0, candidate_string)

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:  # pragma: no cover - external test harness availability
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is not available: {exc}",
        allow_module_level=True,
    )

from core.models import Job  # noqa: E402
from django.contrib.contenttypes.models import ContentType  # noqa: E402

from netbox_proxbox.jobs import (  # noqa: E402
    LEGACY_PROXBOX_RQ_QUEUE,
    PROXBOX_SYNC_QUEUE_NAME,
    is_proxbox_sync_job,
    proxbox_sync_job_q,
)

# (name, queue_name, data) -- deliberately spans every branch of the predicate
# plus the translation traps: a blank queue, whitespace-padded names, jsonb
# payloads that are not objects, and non-Proxbox rows whose name or queue is a
# near miss. ``queue_name`` is NOT NULL in the schema, so blank is the emptiest
# value these rows can carry.
_ROWS = [
    # Proxbox, identified by the data payload regardless of name/queue.
    ("Some Custom Sync Name", "default", {"proxbox_sync": {"params": {}}}),
    ("Renamed By Operator", "low", {"proxbox_sync": {}}),
    # Proxbox, identified by the legacy dedicated queue.
    ("Anything At All", LEGACY_PROXBOX_RQ_QUEUE, None),
    # Proxbox, identified by the default job label on an allowed queue.
    ("Proxbox Sync", PROXBOX_SYNC_QUEUE_NAME, None),
    ("Proxbox Sync", "", None),
    ("  Proxbox Sync  ", "default", None),  # the .strip() trap
    # Proxbox, identified by the targeted per-VM job name.
    ("Proxbox Sync: Virtual machine 100", "default", None),
    ("Proxbox Sync: Virtual machine 7", "high", None),
    # Not Proxbox -- other plugins and core work sharing the default queue.
    ("Report Run", "default", None),
    ("Script: provision", "default", {"script": {}}),
    ("Housekeeping", "", None),
    ("Sync GPON ONTs", "default", {"gpon_sync": {}}),
    # Not Proxbox -- near misses that must not be swept in.
    ("Proxbox Sync Extra", "default", None),
    ("Not Proxbox Sync", "default", None),
    ("Proxbox Sync: Virtual machine abc", "default", None),
    ("Proxbox Sync: Virtual machine", "default", None),
    ("proxbox sync", "default", None),  # case-sensitive by design
    # Not Proxbox -- jsonb ``?`` is also true for a top-level ARRAY holding the
    # string, while the predicate requires a dict. Without the key-transform
    # pairing in proxbox_sync_job_q() this row appears on the page.
    ("Array Payload", "default", ["proxbox_sync"]),
    ("Scalar Payload", "default", "proxbox_sync"),
    # Proxbox -- a dict whose value is JSON null: ``"proxbox_sync" in data`` is
    # True, so the filter must match it too. This is the row that breaks a
    # naive "key transform is not null" translation.
    ("Null Valued", "default", {"proxbox_sync": None}),
]


@pytest.fixture()
def job_rows(db):
    """Create the row matrix, returning them in creation order."""
    object_type = ContentType.objects.get_for_model(Job)
    created = []
    for name, queue_name, data in _ROWS:
        # ``job_id`` is a required unique UUID with no model default, so it has
        # to be supplied explicitly. ``queue_name`` is CharField(blank=True) --
        # NOT NULL at the database level -- so blank is the emptiest value a
        # real row can hold, and the predicate's ``queue_name or ""`` guard
        # exists for unsaved/stub objects rather than for rows like these.
        job = Job.objects.create(
            object_type=object_type,
            job_id=uuid.uuid4(),
            name=name,
            status="errored",
            queue_name=queue_name,
            data=data,
        )
        created.append(job)
    return created


@pytest.mark.django_db
def test_queryset_filter_matches_the_python_predicate(job_rows):
    """The SQL filter and the per-row predicate must select the same jobs."""
    expected = {job.pk for job in job_rows if is_proxbox_sync_job(job)}
    actual = set(
        Job.objects.filter(proxbox_sync_job_q()).values_list("pk", flat=True)
    )

    # Name the disagreements; a bare set comparison makes a drift unreadable.
    names = {job.pk: (job.name, job.queue_name) for job in job_rows}
    assert actual == expected, (
        f"only the SQL filter matched: {[names[pk] for pk in sorted(actual - expected)]}; "
        f"only the predicate matched: {[names[pk] for pk in sorted(expected - actual)]}"
    )


@pytest.mark.django_db
def test_the_matrix_exercises_both_answers(job_rows):
    """Guard the guard: a matrix that is all-Proxbox would prove nothing.

    If every row selected the same way, the parity assertion above would pass
    against a ``Q`` matching everything (or nothing) and silently stop testing.
    """
    verdicts = {is_proxbox_sync_job(job) for job in job_rows}
    assert verdicts == {True, False}


@pytest.mark.django_db
def test_blank_queue_name_is_matched(job_rows):
    """A blank queue must still match: the predicate reads it as ``""``.

    ``queue_name`` is ``CharField(blank=True)`` -- NOT NULL in the database --
    so blank, not SQL NULL, is the emptiest value a real row can carry. The
    ``queue_name__isnull`` branch in the filter is kept as a cheap guard for a
    future schema change and for the stub objects other tests build, but it is
    this case that a live install actually produces.
    """
    matched = set(
        Job.objects.filter(proxbox_sync_job_q()).values_list("pk", flat=True)
    )
    blank_queue_proxbox = [
        job
        for job in job_rows
        if job.queue_name == "" and job.name.strip() == "Proxbox Sync"
    ]
    assert blank_queue_proxbox, "matrix no longer covers the blank-queue case"
    for job in blank_queue_proxbox:
        assert job.pk in matched


@pytest.mark.django_db
def test_a_top_level_json_array_is_not_a_proxbox_job(job_rows):
    """jsonb ``?`` matches an array element; the predicate requires a dict.

    Without the key-transform pairing, a job whose ``data`` is
    ``["proxbox_sync"]`` is rejected by ``is_proxbox_sync_job()`` and yet shown
    on the Proxbox page -- a divergence the dict-only matrix could not see.
    """
    matched = set(
        Job.objects.filter(proxbox_sync_job_q()).values_list("pk", flat=True)
    )
    for job in job_rows:
        if job.name in ("Array Payload", "Scalar Payload"):
            assert not is_proxbox_sync_job(job)
            assert job.pk not in matched


@pytest.mark.django_db
def test_a_dict_with_a_json_null_value_is_a_proxbox_job(job_rows):
    """``"proxbox_sync" in data`` is True when the value is null.

    This is the counterweight to the array case: a translation that demanded a
    non-null *value* would drop it.
    """
    matched = set(
        Job.objects.filter(proxbox_sync_job_q()).values_list("pk", flat=True)
    )
    for job in job_rows:
        if job.name == "Null Valued":
            assert is_proxbox_sync_job(job)
            assert job.pk in matched


@pytest.mark.django_db
def test_unrelated_plugin_jobs_are_excluded(job_rows):
    """The whole point of the page: other plugins' jobs must not appear."""
    matched = set(
        Job.objects.filter(proxbox_sync_job_q()).values_list("pk", flat=True)
    )
    for job in job_rows:
        if job.name in ("Report Run", "Script: provision", "Sync GPON ONTs"):
            assert job.pk not in matched
