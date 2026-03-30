"""Background job for triggering ProxBox sync operations via the FastAPI backend."""

from __future__ import annotations

from typing import Any

from netbox.jobs import JobRunner

from netbox_proxbox.choices import SyncTypeChoices

__all__ = ("ProxboxSyncJob", "proxbox_sync_params_from_job")


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


# Maps sync_type choices to the FastAPI backend path
_SYNC_TYPE_PATH = {
    SyncTypeChoices.DEVICES: "dcim/devices/create",
    SyncTypeChoices.VIRTUAL_MACHINES: "virtualization/virtual-machines/create",
    SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS: "virtualization/virtual-machines/backups/all/create",
}


class ProxboxSyncJob(JobRunner):
    """Trigger a ProxBox sync operation against the FastAPI backend."""

    class Meta:
        name = "Proxbox Sync"

    def run(
        self,
        sync_type: str = SyncTypeChoices.ALL,
        proxmox_endpoint_ids: list[str] | None = None,
        netbox_endpoint_ids: list[str] | None = None,
        **kwargs,
    ):
        # Import here to avoid circular imports at module load time
        from netbox_proxbox.services import sync_full_update_resource, sync_resource

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

        if sync_type == SyncTypeChoices.ALL:
            payload, status = sync_full_update_resource(
                query_params=query_params or None
            )
        else:
            path = _SYNC_TYPE_PATH.get(sync_type)
            if not path:
                raise ValueError(f"Unknown sync_type: {sync_type!r}")
            payload, status = sync_resource(path, query_params=query_params or None)

        if status >= 400:
            detail = payload.get("detail", "Backend returned an error.")
            self.logger.error("Sync failed (HTTP %s): %s", status, detail)
            raise RuntimeError(detail)

        self.logger.info("Sync completed successfully (HTTP %s)", status)
        self.job.data = {"proxbox_sync": {"params": params, "response": payload}}
        self.job.save(update_fields=["data"])
