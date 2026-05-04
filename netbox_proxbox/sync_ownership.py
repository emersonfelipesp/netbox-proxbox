"""Sync ownership claiming / releasing for RQ jobs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from netbox.jobs import Job

SYNC_OWNER_RQ = "rq_job"


def _normalized_job_data(job: Job) -> dict:
    """Return mutable dict job.data, tolerating legacy string/invalid values."""
    raw_data = getattr(job, "data", None)
    if raw_data is None or isinstance(raw_data, dict):
        return raw_data if raw_data is not None else {}
    elif isinstance(raw_data, str):
        try:
            data = json.loads(raw_data) if raw_data else {}
        except (json.JSONDecodeError, TypeError):
            return {}
        return data if isinstance(data, dict) else {}
    else:
        return {}


def _save_job_data(job: Job, data: dict) -> None:
    job.data = data
    job.save(update_fields=["data"])


def _lock_job_for_update(job: Job) -> Job | None:
    """Return the current Job row under select_for_update when ORM support exists."""
    pk = getattr(job, "pk", None)
    manager = getattr(getattr(job, "__class__", object), "objects", None)
    if pk in (None, "") or manager is None:
        return None
    try:
        return manager.select_for_update().get(pk=pk)
    except (AttributeError, TypeError, ValueError):
        return None


def _claim_on_job_instance(job: Job) -> bool:
    import datetime as dt

    data = _normalized_job_data(job)
    proxbox_sync = data.get("proxbox_sync", {})
    if not isinstance(proxbox_sync, dict):
        proxbox_sync = {}
    current_owner = proxbox_sync.get("sync_owner")
    if current_owner and current_owner != SYNC_OWNER_RQ:
        return False
    proxbox_sync["sync_owner"] = SYNC_OWNER_RQ
    proxbox_sync["sync_owner_claimed_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    data["proxbox_sync"] = proxbox_sync
    _save_job_data(job, data)
    return True


def _claim_rq_sync_ownership(job: Job) -> bool:
    """Claim sync ownership for RQ job, using a DB row lock when available."""
    try:
        from django.db import transaction

        with transaction.atomic():
            locked_job = _lock_job_for_update(job)
            if locked_job is None:
                return _claim_on_job_instance(job)
            claimed = _claim_on_job_instance(locked_job)
            if claimed:
                job.data = locked_job.data
            return claimed
    except (ImportError, RuntimeError, AttributeError):
        return _claim_on_job_instance(job)


def _release_rq_sync_ownership(job: Job) -> None:
    """Release RQ sync ownership if we are the owner."""
    data = _normalized_job_data(job)
    proxbox_sync = data.get("proxbox_sync", {})
    if not isinstance(proxbox_sync, dict):
        return
    if proxbox_sync.get("sync_owner") == SYNC_OWNER_RQ:
        del proxbox_sync["sync_owner"]
        if proxbox_sync.get("sync_owner_claimed_at"):
            del proxbox_sync["sync_owner_claimed_at"]
        data["proxbox_sync"] = proxbox_sync
        _save_job_data(job, data)
