"""Pydantic V2 schemas for Proxmox storage API responses."""

from __future__ import annotations

from pydantic import Field, field_validator

from netbox_proxbox.schemas._base import ProxboxBaseModel, ProxboxLenientModel
from netbox_proxbox.schemas._formatters import format_bytes


class StorageUsage(ProxboxBaseModel):
    """Computed storage usage metrics for display."""

    used_bytes: int = 0
    total_bytes: int = 0
    avail_bytes: int = 0
    used_pct: float = 0.0
    used_label: str = "0.00 B"
    total_label: str = "0.00 B"
    avail_label: str = "0.00 B"


class ProxmoxStorageRecord(ProxboxLenientModel):
    """One storage record from ``/proxmox/storage`` or ``/proxmox/cluster/resources``."""

    storage: str | None = None
    name: str | None = None
    cluster: str | None = None
    storage_type: str | None = Field(None, alias="type")
    content: str | None = None
    nodes: str | None = None
    shared: int | None = None
    enabled: int | None = None
    total: int | None = None
    used: int | None = None
    avail: int | None = None
    maxdisk: int | None = None
    disk: int | None = None
    max_size: int | None = None
    size: int | None = None
    available: int | None = None
    free: int | None = None

    @field_validator(
        "total",
        "used",
        "avail",
        "maxdisk",
        "disk",
        "max_size",
        "size",
        "available",
        "free",
        "shared",
        "enabled",
        mode="before",
    )
    @classmethod
    def _coerce_int(cls, v: object) -> int | None:
        if v is None:
            return None
        try:
            return int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    @property
    def effective_name(self) -> str:
        return self.storage or self.name or ""

    @property
    def effective_total(self) -> int:
        for value in (self.total, self.maxdisk, self.max_size, self.size):
            if value is not None:
                return value
        return 0

    @property
    def effective_used(self) -> int:
        for value in (self.used, self.disk):
            if value is not None:
                return value
        return 0

    @property
    def effective_avail(self) -> int:
        avail = next(
            (
                value
                for value in (self.avail, self.available, self.free)
                if value is not None
            ),
            None,
        )
        if avail is not None:
            return avail
        return max(self.effective_total - self.effective_used, 0)

    def to_usage_dict(self) -> StorageUsage:
        """Compute storage usage metrics. Replaces ``_usage_from_record()`` in ``views/storage.py``."""
        total = self.effective_total
        used = self.effective_used
        avail = self.effective_avail
        used_pct = round((used / total) * 100.0, 2) if total > 0 else 0.0
        return StorageUsage(
            used_bytes=used,
            total_bytes=total,
            avail_bytes=avail,
            used_pct=used_pct,
            used_label=format_bytes(used),
            total_label=format_bytes(total),
            avail_label=format_bytes(avail),
        )

    def node_list(self) -> list[str]:
        """Return the nodes field as a list of strings. Replaces ``_parse_nodes()`` in ``views/storage.py``."""
        if not self.nodes:
            return []
        return [part.strip() for part in str(self.nodes).split(",") if part.strip()]


class StorageContentRecord(ProxboxLenientModel):
    """One content item from ``/proxmox/nodes/{node}/storage/{name}/content``."""

    volid: str | None = None
    content: str | None = None
    format: str | None = None
    size: int | None = None
    vmid: int | None = None
    parent: str | None = None

    @field_validator("size", "vmid", mode="before")
    @classmethod
    def _coerce_int(cls, v: object) -> int | None:
        if v is None:
            return None
        try:
            return int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
