"""Helper functions for the schedule-sync views."""

from __future__ import annotations

from django.db.models import Q
from django.http import HttpRequest

from core.choices import JobStatusChoices
from core.models import Job
from netbox_proxbox.jobs import (
    PROXBOX_SYNC_QUEUE_NAME,
    is_proxbox_sync_job,
    proxbox_sync_params_from_job,
)
from netbox_proxbox.models import NetBoxEndpoint, ProxmoxEndpoint


def build_initial_from_job(request: HttpRequest, edit_job_id: str) -> dict:
    """Build form initial data from an existing scheduled job (for the edit flow)."""
    initial: dict = {}
    try:
        job = Job.objects.restrict(request.user, "view").get(pk=edit_job_id)
    except Job.DoesNotExist:
        return initial

    if not is_proxbox_sync_job(job):
        return initial

    params = proxbox_sync_params_from_job(job)
    initial["job_name"] = job.name or ""
    initial["sync_types"] = params.get("sync_types", [])
    proxmox_endpoint_ids = params.get("proxmox_endpoint_ids", [])
    netbox_endpoint_ids = params.get("netbox_endpoint_ids", [])
    if proxmox_endpoint_ids:
        initial["proxmox_endpoints"] = list(
            ProxmoxEndpoint.objects.filter(pk__in=proxmox_endpoint_ids)
        )
    if netbox_endpoint_ids:
        initial["netbox_endpoints"] = list(
            NetBoxEndpoint.objects.filter(pk__in=netbox_endpoint_ids)
        )
    if job.scheduled:
        initial["schedule_at"] = job.scheduled
    if job.interval:
        interval_minutes = job.interval
        if interval_minutes >= 60 * 24 * 7:
            initial["interval_value"] = interval_minutes // (60 * 24 * 7)
            initial["interval_unit"] = "weeks"
        elif interval_minutes >= 60 * 24:
            initial["interval_value"] = interval_minutes // (60 * 24)
            initial["interval_unit"] = "days"
        elif interval_minutes >= 60:
            initial["interval_value"] = interval_minutes // 60
            initial["interval_unit"] = "hours"
        else:
            initial["interval_value"] = interval_minutes
            initial["interval_unit"] = "minutes"
    return initial


def get_scheduled_jobs_list(request: HttpRequest) -> list[dict]:
    """Return a list of dicts describing active Proxbox sync scheduled jobs.

    Includes completed recurring jobs (interval set) because a completed recurring
    job still represents an active schedule — the next run is queued as a new job.
    """
    scheduled_jobs: list[dict] = []
    # Include non-completed jobs OR completed jobs that are recurring (have interval).
    candidates = (
        Job.objects.restrict(request.user, "view")
        .filter(Q(queue_name=PROXBOX_SYNC_QUEUE_NAME) | Q(data__has_key="proxbox_sync"))
        .filter(
            Q(
                status__in=[
                    JobStatusChoices.STATUS_PENDING,
                    JobStatusChoices.STATUS_SCHEDULED,
                    JobStatusChoices.STATUS_RUNNING,
                    JobStatusChoices.STATUS_ERRORED,
                    JobStatusChoices.STATUS_FAILED,
                ]
            )
            | Q(status=JobStatusChoices.STATUS_COMPLETED, interval__isnull=False)
        )
        .order_by("-created")
    )
    for job in candidates.iterator(chunk_size=64):
        if not is_proxbox_sync_job(job):
            continue
        params = proxbox_sync_params_from_job(job)
        scheduled_jobs.append(
            {
                "id": job.pk,
                "pk": job.pk,
                "name": job.name,
                "sync_types": params.get("sync_types", []),
                "schedule": job.scheduled,
                "interval": job.interval,
                "status": job.status,
            }
        )
    return scheduled_jobs
