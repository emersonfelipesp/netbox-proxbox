"""Pydantic V2 schemas for sync job parameters and results."""

from __future__ import annotations

from pydantic import Field

from netbox_proxbox.schemas._base import ProxboxBaseModel


class SyncJobParams(ProxboxBaseModel):
    """Parameters block stored in ``job.data['proxbox_sync']['params']``."""

    sync_types: list[str] = Field(default_factory=list)
    proxmox_endpoint_ids: list[str] = Field(default_factory=list)
    netbox_endpoint_ids: list[str] = Field(default_factory=list)
    netbox_vm_ids: list[str] = Field(default_factory=list)
    batch_object_type: str | None = None
    batch_object_ids: list[str] = Field(default_factory=list)
    run_id: str | None = None


class SyncJobData(ProxboxBaseModel):
    """The ``proxbox_sync`` block stored in ``job.data``."""

    params: SyncJobParams = Field(default_factory=SyncJobParams)
    runtime_seconds: float | None = None
    response: dict[str, object] | None = None

    @classmethod
    def from_job(cls, job: object) -> SyncJobData:
        """Parse ``job.data['proxbox_sync']`` into a typed model with safe fallbacks."""
        data = getattr(job, "data", None)
        if not isinstance(data, dict):
            data = {}
        block = data.get("proxbox_sync")
        if not isinstance(block, dict):
            block = {}
        return cls.model_validate(block)


class ClusterSyncResult(ProxboxBaseModel):
    """Return value from ``services/sync_cluster.sync_cluster_and_nodes()``."""

    success: bool = False
    endpoint_id: int | None = None
    endpoint_name: str = ""
    clusters_created: int = 0
    clusters_updated: int = 0
    nodes_created: int = 0
    nodes_updated: int = 0
    nodes_deleted: int = 0
    mode_updated: bool = False
    error: str | None = None
