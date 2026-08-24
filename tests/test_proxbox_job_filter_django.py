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
# plus the translation traps: a NULL queue, whitespace-padded names, and
# non-Proxbox rows whose name or queue is a near miss.
_ROWS = [
    # Proxbox, identified by the data payload regardless of name/queue.
    ("Some Custom Sync Name", "default", {"proxbox_sync": {"params": {}}}),
    ("Renamed By Operator", "low", {"proxbox_sync": {}}),
    # Proxbox, identified by the legacy dedicated queue.
    ("Anything At All", LEGACY_PROXBOX_RQ_QUEUE, None),
    # Proxbox, identified by the default job label on an allowed queue.
    ("Proxbox Sync", PROXBOX_SYNC_QUEUE_NAME, None),
    ("Proxbox Sync", "", None),
    ("Proxbox Sync", None, None),  # the SQL NULL trap
    ("  Proxbox Sync  ", "default", None),  # the .strip() trap
    # Proxbox, identified by the targeted per-VM job name.
    ("Proxbox Sync: Virtual machine 100", "default", None),
    ("Proxbox Sync: Virtual machine 7", "high", None),
    # Not Proxbox -- other plugins and core work sharing the default queue.
    ("Report Run", "default", None),
    ("Script: provision", "default", {"script": {}}),
    ("Housekeeping", None, None),
    ("Sync GPON ONTs", "default", {"gpon_sync": {}}),
    # Not Proxbox -- near misses that must not be swept in.
    ("Proxbox Sync Extra", "default", None),
    ("Not Proxbox Sync", "default", None),
    ("Proxbox Sync: Virtual machine abc", "default", None),
    ("Proxbox Sync: Virtual machine", "default", None),
    ("proxbox sync", "default", None),  # case-sensitive by design
]


@pytest.fixture()
def job_rows(db):
    """Create the row matrix, returning them in creation order."""
    object_type = ContentType.objects.get_for_model(Job)
    created = []
    for name, queue_name, data in _ROWS:
        job = Job.objects.create(
            object_type=object_type,
            name=name,
            status="errored",
            data=data,
        )
        # ``queue_name`` has a model default, so NULL/blank must be forced in
        # afterwards with an UPDATE rather than passed to create().
        Job.objects.filter(pk=job.pk).update(queue_name=queue_name)
        job.refresh_from_db()
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
def test_null_queue_name_is_matched(job_rows):
    """A NULL queue must still match: the predicate reads it as ``""``.

    ``Q(queue_name__in=[...])`` never matches SQL NULL, so this is the branch a
    naive translation of the predicate drops -- and it drops it silently, since
    the rows simply stop appearing on the page.
    """
    matched = set(
        Job.objects.filter(proxbox_sync_job_q()).values_list("pk", flat=True)
    )
    null_queue_proxbox = [
        job
        for job in job_rows
        if job.queue_name in (None, "") and job.name.strip() == "Proxbox Sync"
    ]
    assert null_queue_proxbox, "matrix no longer covers the NULL/blank queue case"
    for job in null_queue_proxbox:
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
