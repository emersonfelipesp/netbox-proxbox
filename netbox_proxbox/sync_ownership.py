"""Sync ownership claiming / releasing for RQ jobs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from netbox.jobs import Job

SYNC_OWNER_RQ = "rq_job"


def _claim_rq_sync_ownership(job: Job) -> bool:
    """Atomically claim sync ownership for RQ job. Returns True if claimed, False if already taken."""
    import datetime as dt

    raw_data = getattr(job, "data", None)
    if raw_data is None or isinstance(raw_data, dict):
        data = raw_data if raw_data is not None else {}
    elif isinstance(raw_data, str):
        try:
            data = json.loads(raw_data) if raw_data else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
    else:
        data = {}
    proxbox_sync = data.get("proxbox_sync", {})
    current_owner = proxbox_sync.get("sync_owner")
    if current_owner and current_owner != SYNC_OWNER_RQ:
        return False
    proxbox_sync["sync_owner"] = SYNC_OWNER_RQ
    proxbox_sync["sync_owner_claimed_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    data["proxbox_sync"] = proxbox_sync
    job.data = data
    job.save(update_fields=["data"])
    return True


def _release_rq_sync_ownership(job: Job) -> None:
    """Release RQ sync ownership if we are the owner."""
    raw_data = getattr(job, "data", None)
    if raw_data is None or isinstance(raw_data, dict):
        data = raw_data if raw_data is not None else {}
    elif isinstance(raw_data, str):
        try:
            data = json.loads(raw_data) if raw_data else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
    else:
        return
    proxbox_sync = data.get("proxbox_sync", {})
    if proxbox_sync.get("sync_owner") == SYNC_OWNER_RQ:
        del proxbox_sync["sync_owner"]
        if proxbox_sync.get("sync_owner_claimed_at"):
            del proxbox_sync["sync_owner_claimed_at"]
        data["proxbox_sync"] = proxbox_sync
        job.data = data
        job.save(update_fields=["data"])
