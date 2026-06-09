"""Helpers for homepage quick-schedule banner (detect recurring All sync, default run times)."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser
    from django.contrib.auth.models import AnonymousUser
else:
    AbstractBaseUser = Any
    AnonymousUser = Any

QUICK_SCHEDULE_DEFAULT_JOB_NAME = _("Proxbox Full Sync")

__all__ = (
    "QUICK_SCHEDULE_DEFAULT_JOB_NAME",
    "has_recurring_proxbox_sync_all",
    "next_local_3am",
    "quick_schedule_home_form_kwargs",
)


def next_local_3am() -> datetime:
    """Next local wall-clock 03:00 after ``local_now()`` (same timezone as schedule form)."""
    now = local_now()
    tz = now.tzinfo
    today_3am = datetime.combine(now.date(), time(3, 0), tzinfo=tz)
    if now >= today_3am:
        return datetime.combine(now.date() + timedelta(days=1), time(3, 0), tzinfo=tz)
    return today_3am


def has_recurring_proxbox_sync_all(user: AbstractBaseUser | AnonymousUser) -> bool:
    """
    True if any live recurring Proxbox job exists whose sync types normalize to ``[all]``.

    Uses an unrestricted query because this answers a system-wide question
    ("is recurring full-sync configured?"), not a per-user visibility question.
    Object-level permissions on ``core.view_job`` can hide the scheduled row
    from ``restrict()``, causing the quick-schedule banner to re-appear even
    though a daily schedule already exists.

    Also includes ``completed`` jobs: when a recurring job finishes, the old row
    becomes ``completed`` while a new ``scheduled`` row is created for the next run.
    If re-enqueueing fails (e.g. duplicate ``job_id`` kwarg), only the ``completed``
    row remains.  A completed recurring job still represents an active schedule.
    Failed/errored rows are excluded — those indicate a cancelled or broken schedule.
    """
    active_statuses = (
        *JobStatusChoices.ENQUEUED_STATE_CHOICES,
        JobStatusChoices.STATUS_COMPLETED,
    )
    candidates = Job.objects.filter(
        interval__isnull=False,
        status__in=active_statuses,
    ).filter(
        Q(queue_name=PROXBOX_SYNC_QUEUE_NAME)
        | Q(queue_name=LEGACY_PROXBOX_RQ_QUEUE)
        | Q(data__has_key="proxbox_sync")
    )
    for job in candidates.iterator(chunk_size=64):
        if not is_proxbox_sync_job(job):
            continue
        if proxbox_sync_params_from_job(job)["sync_types"] == [SyncTypeChoices.ALL]:
            return True
    return False


def quick_schedule_home_form_kwargs() -> dict[str, object]:
    """Constructor kwargs for ``ScheduleSyncForm`` with All + daily + next 03:00 local defaults."""
    from netbox_proxbox.models import (
        ProxmoxEndpoint,
    )  # local to avoid circular import in tests

    all_proxmox_pks = list(
        ProxmoxEndpoint.objects.filter(enabled=True).values_list("pk", flat=True)
    )
    return {
        "initial": {
            "sync_types": [SyncTypeChoices.ALL],
            "schedule_at": next_local_3am(),
            "job_name": QUICK_SCHEDULE_DEFAULT_JOB_NAME,
            "proxmox_endpoints": all_proxmox_pks,
        },
        "initial_interval": 60 * 24,
        "use_bootstrap_sync_checkboxes": True,
    }
