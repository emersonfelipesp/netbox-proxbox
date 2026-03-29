"""Background job for triggering ProxBox sync operations via the FastAPI backend."""

from netbox.jobs import JobRunner

from netbox_proxbox.choices import SyncTypeChoices

__all__ = ("ProxboxSyncJob",)

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

    def run(self, sync_type: str = SyncTypeChoices.ALL, **kwargs):
        # Import here to avoid circular imports at module load time
        from netbox_proxbox.views.sync import sync_full_update_resource, sync_resource

        self.logger.info("Starting Proxbox sync: %s", sync_type)

        if sync_type == SyncTypeChoices.ALL:
            payload, status = sync_full_update_resource()
        else:
            path = _SYNC_TYPE_PATH.get(sync_type)
            if not path:
                raise ValueError(f"Unknown sync_type: {sync_type!r}")
            payload, status = sync_resource(path)

        if status >= 400:
            detail = payload.get("detail", "Backend returned an error.")
            self.logger.error("Sync failed (HTTP %s): %s", status, detail)
            raise RuntimeError(detail)

        self.logger.info("Sync completed successfully (HTTP %s)", status)
        self.job.data = payload
        self.job.save()
