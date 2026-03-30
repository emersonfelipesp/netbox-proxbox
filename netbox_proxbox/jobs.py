"""Background job for triggering ProxBox sync operations via the FastAPI backend."""

from __future__ import annotations

from typing import Any

from netbox.jobs import JobRunner

from netbox_proxbox.choices import SyncTypeChoices

PROXBOX_SYNC_QUEUE_NAME = "netbox_proxbox.sync"

# RQ wall-clock limit for the whole job. Must exceed NetBox's default ``RQ_DEFAULT_TIMEOUT``
# (often 300s) and the HTTP stream read budget between chunks (3600s in ``run_sync_stream``).
# Override per enqueue via ``job_timeout=...`` if full syncs routinely run longer.
PROXBOX_SYNC_JOB_TIMEOUT = 7200

__all__ = (
    "PROXBOX_SYNC_QUEUE_NAME",
    "PROXBOX_SYNC_JOB_TIMEOUT",
    "ProxboxSyncJob",
    "is_proxbox_sync_job",
    "proxbox_sync_params_from_job",
)


def proxbox_sync_params_from_job(job: Any) -> dict[str, Any]:
    """Rebuild ProxboxSyncJob.enqueue kwargs from job.data (with safe fallbacks)."""
    data = job.data if isinstance(getattr(job, "data", None), dict) else {}
    block = data.get("proxbox_sync")
    if not isinstance(block, dict):
        block = {}
    params = block.get("params")
    if not isinstance(params, dict):
        return {
            "sync_type": SyncTypeChoices.ALL,
            "proxmox_endpoint_ids": [],
            "netbox_endpoint_ids": [],
        }
    return {
        "sync_type": params.get("sync_type") or SyncTypeChoices.ALL,
        "proxmox_endpoint_ids": list(params.get("proxmox_endpoint_ids") or []),
        "netbox_endpoint_ids": list(params.get("netbox_endpoint_ids") or []),
    }


# Maps sync_type choices to the FastAPI backend base path (before ``/stream``).
_SYNC_TYPE_PATH = {
    SyncTypeChoices.DEVICES: "dcim/devices/create",
    SyncTypeChoices.VIRTUAL_MACHINES: "virtualization/virtual-machines/create",
    SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS: "virtualization/virtual-machines/backups/all/create",
    SyncTypeChoices.VIRTUAL_MACHINES_DISKS: "virtualization/virtual-machines/virtual-disks/create",
}


def _sync_stream_path(sync_type: str) -> str:
    """Return proxbox-api SSE path for a scheduled sync type."""
    if sync_type == SyncTypeChoices.ALL:
        return "full-update/stream"
    base = _SYNC_TYPE_PATH.get(sync_type)
    if not base:
        raise ValueError(f"Unknown sync_type: {sync_type!r}")
    return f"{base.rstrip('/')}/stream"


class ProxboxSyncJob(JobRunner):
    """Trigger a ProxBox sync operation against the FastAPI backend."""

    class Meta:
        name = "Proxbox Sync"

    @classmethod
    def enqueue(cls, *args, **kwargs):
        """Enqueue like other ``JobRunner`` jobs, but with a long RQ ``job_timeout`` by default."""
        kwargs.setdefault("job_timeout", PROXBOX_SYNC_JOB_TIMEOUT)
        return super().enqueue(*args, **kwargs)

    def run(
        self,
        sync_type: str = SyncTypeChoices.ALL,
        proxmox_endpoint_ids: list[str] | None = None,
        netbox_endpoint_ids: list[str] | None = None,
        **kwargs,
    ):
        """Run sync by consuming proxbox-api SSE until ``complete``; store params and response on ``job.data``."""
        # Import here to avoid circular imports at module load time
        from netbox_proxbox.services import run_sync_stream

        params = {
            "sync_type": sync_type,
            "proxmox_endpoint_ids": list(proxmox_endpoint_ids or []),
            "netbox_endpoint_ids": list(netbox_endpoint_ids or []),
        }
        self.job.data = {"proxbox_sync": {"params": params}}
        self.job.save(update_fields=["data"])

        self.logger.info("Starting Proxbox sync: %s", sync_type)
        if proxmox_endpoint_ids:
            self.logger.info("Proxmox endpoints: %s", proxmox_endpoint_ids)
        if netbox_endpoint_ids:
            self.logger.info("NetBox endpoints: %s", netbox_endpoint_ids)

        query_params = {}
        if proxmox_endpoint_ids:
            query_params["proxmox_endpoint_ids"] = ",".join(proxmox_endpoint_ids)
        if netbox_endpoint_ids:
            query_params["netbox_endpoint_ids"] = ",".join(netbox_endpoint_ids)
        if sync_type == SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS:
            query_params["delete_nonexistent_backup"] = True

        stream_path = _sync_stream_path(sync_type)
        payload, status = run_sync_stream(
            stream_path,
            query_params=query_params or None,
        )

        if status >= 400:
            detail = payload.get("detail", "Backend returned an error.")
            self.logger.error("Sync failed (HTTP %s): %s", status, detail)
            raise RuntimeError(detail)

        self.logger.info("Sync completed successfully (HTTP %s)", status)
        self.job.data = {"proxbox_sync": {"params": params, "response": payload}}
        self.job.save(update_fields=["data"])


def is_proxbox_sync_job(job: Any) -> bool:
    """True if this core Job row is a Proxbox sync (including user-defined job names)."""
    qn = getattr(job, "queue_name", None) or ""
    if qn == PROXBOX_SYNC_QUEUE_NAME:
        return True
    # Legacy rows: queue may be unset while the job still used the default display name.
    default_label = getattr(ProxboxSyncJob.Meta, "name", "Proxbox Sync")
    return not qn and getattr(job, "name", None) == default_label
