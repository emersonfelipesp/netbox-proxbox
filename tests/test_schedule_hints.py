"""Tests for homepage schedule detection and next-3am default."""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.fixture
def schedule_hints(monkeypatch):
    """Load schedule_hints.py with NetBox/Django deps stubbed."""
    core_choices = types.ModuleType("core.choices")
    core_choices.JobStatusChoices = SimpleNamespace(
        ENQUEUED_STATE_CHOICES=("pending", "scheduled", "running")
    )
    monkeypatch.setitem(sys.modules, "core.choices", core_choices)

    class Job:
        objects = None

    core_models = types.ModuleType("core.models")
    core_models.Job = Job
    monkeypatch.setitem(sys.modules, "core.models", core_models)

    utilities_datetime = types.ModuleType("utilities.datetime")
    utilities_datetime.local_now = lambda: datetime(
        2026, 6, 15, 10, 0, 0, tzinfo=timezone.utc
    )
    monkeypatch.setitem(sys.modules, "utilities.datetime", utilities_datetime)

    class Q:
        def __init__(self, *args, **kwargs):
            pass

        def __or__(self, other):
            return self

    django_models = types.ModuleType("django.db.models")
    django_models.Q = Q
    monkeypatch.setitem(sys.modules, "django.db.models", django_models)

    django_utils = types.ModuleType("django.utils")
    django_utils_translation = types.ModuleType("django.utils.translation")
    django_utils_translation.gettext_lazy = lambda s: s
    django_utils.translation = django_utils_translation
    monkeypatch.setitem(sys.modules, "django.utils", django_utils)
    monkeypatch.setitem(
        sys.modules, "django.utils.translation", django_utils_translation
    )

    netbox_constants = types.ModuleType("netbox.constants")
    netbox_constants.RQ_QUEUE_DEFAULT = "default"
    monkeypatch.setitem(sys.modules, "netbox.constants", netbox_constants)

    netbox_jobs = types.ModuleType("netbox.jobs")

    class JobRunner:
        pass

    netbox_jobs.JobRunner = JobRunner
    monkeypatch.setitem(sys.modules, "netbox.jobs", netbox_jobs)

    choices_mod = types.ModuleType("netbox_proxbox.choices")
    choices_mod.SyncTypeChoices = SimpleNamespace(
        BACKUP_ROUTINES="backup-routines",
        REPLICATIONS="replications",
        DEVICES="devices",
        STORAGE="storage",
        VIRTUAL_MACHINES="virtual-machines",
        VIRTUAL_MACHINES_BACKUPS="vm-backups",
        VIRTUAL_MACHINES_DISKS="vm-disks",
        VIRTUAL_MACHINES_SNAPSHOTS="vm-snapshots",
        NETWORK_INTERFACES="network-interfaces",
        IP_ADDRESSES="ip-addresses",
        ALL="all",
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.choices", choices_mod)

    root = Path(__file__).resolve().parents[1]
    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(root / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)

    sys.modules.pop("netbox_proxbox.jobs", None)
    jobs_path = root / "netbox_proxbox" / "jobs.py"
    jobs_spec = importlib.util.spec_from_file_location("netbox_proxbox.jobs", jobs_path)
    jobs_mod = importlib.util.module_from_spec(jobs_spec)
    assert jobs_spec and jobs_spec.loader
    sys.modules["netbox_proxbox.jobs"] = jobs_mod
    jobs_spec.loader.exec_module(jobs_mod)

    sys.modules.pop("netbox_proxbox.schedule_hints", None)
    hints_path = root / "netbox_proxbox" / "schedule_hints.py"
    hints_spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.schedule_hints", hints_path
    )
    hints_mod = importlib.util.module_from_spec(hints_spec)
    assert hints_spec and hints_spec.loader
    sys.modules["netbox_proxbox.schedule_hints"] = hints_mod
    hints_spec.loader.exec_module(hints_mod)
    return hints_mod


def test_next_local_3am_same_day(schedule_hints):
    with patch.object(
        schedule_hints,
        "local_now",
        return_value=datetime(2026, 6, 15, 1, 30, 0, tzinfo=timezone.utc),
    ):
        t = schedule_hints.next_local_3am()
    assert t == datetime(2026, 6, 15, 3, 0, 0, tzinfo=timezone.utc)


def test_next_local_3am_next_day(schedule_hints):
    with patch.object(
        schedule_hints,
        "local_now",
        return_value=datetime(2026, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
    ):
        t = schedule_hints.next_local_3am()
    assert t == datetime(2026, 6, 16, 3, 0, 0, tzinfo=timezone.utc)


def _make_job(**kwargs):
    return SimpleNamespace(**kwargs)


def test_has_recurring_proxbox_sync_all_finds_all_sync(schedule_hints, monkeypatch):
    job = _make_job(
        interval=1440,
        status="scheduled",
        queue_name=schedule_hints.PROXBOX_SYNC_QUEUE_NAME,
        data={"proxbox_sync": {"params": {"sync_types": ["all"]}}},
    )

    class QS:
        def restrict(self, user, action):
            return self

        def filter(self, *a, **k):
            return self

        def iterator(self, chunk_size=64):
            yield job

    monkeypatch.setattr(schedule_hints.Job, "objects", QS())

    assert schedule_hints.has_recurring_proxbox_sync_all(object()) is True


def test_has_recurring_proxbox_sync_all_ignores_devices_only(
    schedule_hints, monkeypatch
):
    job = _make_job(
        interval=1440,
        status="scheduled",
        queue_name=schedule_hints.PROXBOX_SYNC_QUEUE_NAME,
        data={"proxbox_sync": {"params": {"sync_types": ["devices"]}}},
    )

    class QS:
        def restrict(self, user, action):
            return self

        def filter(self, *a, **k):
            return self

        def iterator(self, chunk_size=64):
            yield job

    monkeypatch.setattr(schedule_hints.Job, "objects", QS())

    assert schedule_hints.has_recurring_proxbox_sync_all(object()) is False


def test_has_recurring_proxbox_sync_all_false_when_no_candidates(
    schedule_hints, monkeypatch
):
    """DB layer excludes non-enqueued rows; empty queryset implies no live recurring All job."""

    class EmptyQS:
        def restrict(self, user, action):
            return self

        def filter(self, *a, **k):
            return self

        def iterator(self, chunk_size=64):
            yield from ()

    monkeypatch.setattr(schedule_hints.Job, "objects", EmptyQS())

    assert schedule_hints.has_recurring_proxbox_sync_all(object()) is False


def test_has_recurring_proxbox_sync_all_detects_default_name_job_without_metadata(
    schedule_hints, monkeypatch
):
    job = _make_job(
        interval=1440,
        status="scheduled",
        queue_name=schedule_hints.PROXBOX_SYNC_QUEUE_NAME,
        name="Proxbox Sync",
        data={},
    )

    class QS:
        def restrict(self, user, action):
            return self

        def filter(self, *a, **k):
            return self

        def iterator(self, chunk_size=64):
            yield job

    monkeypatch.setattr(schedule_hints.Job, "objects", QS())
    monkeypatch.setattr(
        schedule_hints,
        "proxbox_sync_params_from_job",
        lambda candidate: {"sync_types": ["all"]},
    )

    assert schedule_hints.has_recurring_proxbox_sync_all(object()) is True


def test_quick_schedule_home_form_kwargs(schedule_hints, monkeypatch):
    monkeypatch.setattr(
        schedule_hints,
        "next_local_3am",
        lambda: datetime(2026, 6, 16, 3, 0, 0, tzinfo=timezone.utc),
    )
    kw = schedule_hints.quick_schedule_home_form_kwargs()
    assert kw["initial"]["sync_types"] == ["all"]
    assert kw["initial"]["schedule_at"] == datetime(
        2026, 6, 16, 3, 0, 0, tzinfo=timezone.utc
    )
    assert kw["initial"]["job_name"] == "Proxbox Full Sync"
    assert kw["use_bootstrap_sync_checkboxes"] is True
    assert kw["initial_interval"] == 60 * 24
