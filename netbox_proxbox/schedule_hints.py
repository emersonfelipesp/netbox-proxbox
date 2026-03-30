"""Helpers for homepage quick-schedule banner (detect recurring All sync, default run times)."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core.choices import JobStatusChoices
from core.models import Job
from utilities.datetime import local_now

from netbox_proxbox.choices import SyncTypeChoices
from netbox_proxbox.jobs import (
    LEGACY_PROXBOX_RQ_QUEUE,
    PROXBOX_SYNC_QUEUE_NAME,
    is_proxbox_sync_job,
    proxbox_sync_params_from_job,
)

QUICK_SCHEDULE_DEFAULT_JOB_NAME = _("Proxbox Full Sync")

__all__ = (
    "QUICK_SCHEDULE_DEFAULT_JOB_NAME",
    "has_recurring_proxbox_sync_all",
    "next_local_3am",
    "quick_schedule_home_form_kwargs",
)


def next_local_3am():
    """Next local wall-clock 03:00 after ``local_now()`` (same timezone as schedule form)."""
    now = local_now()
    tz = now.tzinfo
    today_3am = datetime.combine(now.date(), time(3, 0), tzinfo=tz)
    if now >= today_3am:
        return datetime.combine(now.date() + timedelta(days=1), time(3, 0), tzinfo=tz)
    return today_3am


def has_recurring_proxbox_sync_all(user) -> bool:
    """
    True if the user can see a live recurring Proxbox job whose sync types normalize to ``[all]``.
    """
    candidates = (
        Job.objects.restrict(user, "view")
        .filter(
            interval__isnull=False,
            status__in=JobStatusChoices.ENQUEUED_STATE_CHOICES,
        )
        .filter(
            Q(queue_name=PROXBOX_SYNC_QUEUE_NAME)
            | Q(queue_name=LEGACY_PROXBOX_RQ_QUEUE)
            | Q(data__has_key="proxbox_sync")
        )
    )
    for job in candidates.iterator(chunk_size=64):
        if not is_proxbox_sync_job(job):
            continue
        if proxbox_sync_params_from_job(job)["sync_types"] == [SyncTypeChoices.ALL]:
            return True
    return False


def quick_schedule_home_form_kwargs() -> dict:
    """Constructor kwargs for ``ScheduleSyncForm`` with All + daily + next 03:00 local defaults."""
    return {
        "initial": {
            "sync_types": [SyncTypeChoices.ALL],
            "schedule_at": next_local_3am(),
            "job_name": QUICK_SCHEDULE_DEFAULT_JOB_NAME,
        },
        "initial_interval": 60 * 24,
        "use_bootstrap_sync_checkboxes": True,
    }
