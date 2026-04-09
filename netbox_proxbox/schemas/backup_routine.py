"""Pydantic V2 schemas for Proxmox backup routines synced via the FastAPI backend."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from netbox_proxbox.schemas._base import ProxboxBaseModel, ProxboxLenientModel
from netbox_proxbox.schemas._enums import (
    BackupMode,
    CompressionAlgorithm,
    NotificationMode,
    PBSChangeDetectionMode,
)
from netbox_proxbox.schemas.schedule_parser import parse_systemd_calendar_to_datetime


# ------------------------------------------------------------------
# Retention parsing helpers
# ------------------------------------------------------------------


def parse_prune_backups(prune_backups: str | None) -> dict[str, int | bool | None]:
    """
    Parse a vzdump prune-backups string into individual retention fields.

    Examples:
        "keep-last=1"                    -> {"keep_last": 1, ...}
        "keep-last=1,keep-daily=7"      -> {"keep_last": 1, "keep_daily": 7, ...}
        "keep-all"                       -> {"keep_all": True, ...}
    """
    if not prune_backups:
        return {
            "keep_last": None,
            "keep_daily": None,
            "keep_weekly": None,
            "keep_monthly": None,
            "keep_yearly": None,
            "keep_all": None,
        }

    result: dict[str, int | bool | None] = {
        "keep_last": None,
        "keep_daily": None,
        "keep_weekly": None,
        "keep_monthly": None,
        "keep_yearly": None,
        "keep_all": None,
    }

    parts = [p.strip() for p in prune_backups.split(",")]
    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            key = key.strip().lower()
            value = value.strip()
            if key == "keep-last":
                result["keep_last"] = int(value) if value.isdigit() else None
            elif key == "keep-daily":
                result["keep_daily"] = int(value) if value.isdigit() else None
            elif key == "keep-weekly":
                result["keep_weekly"] = int(value) if value.isdigit() else None
            elif key == "keep-monthly":
                result["keep_monthly"] = int(value) if value.isdigit() else None
            elif key == "keep-yearly":
                result["keep_yearly"] = int(value) if value.isdigit() else None
        elif part.strip().lower() == "keep-all":
            result["keep_all"] = True

    return result


def format_prune_backups(
    keep_last: int | None = None,
    keep_daily: int | None = None,
    keep_weekly: int | None = None,
    keep_monthly: int | None = None,
    keep_yearly: int | None = None,
    keep_all: bool | None = None,
) -> str | None:
    """Build a vzdump prune-backups string from individual retention values."""
    parts = []
    if keep_all is True:
        parts.append("keep-all")
    if keep_last is not None:
        parts.append(f"keep-last={keep_last}")
    if keep_daily is not None:
        parts.append(f"keep-daily={keep_daily}")
    if keep_weekly is not None:
        parts.append(f"keep-weekly={keep_weekly}")
    if keep_monthly is not None:
        parts.append(f"keep-monthly={keep_monthly}")
    if keep_yearly is not None:
        parts.append(f"keep-yearly={keep_yearly}")
    return ",".join(parts) if parts else None


# ------------------------------------------------------------------
# Proxmox API response models
# ------------------------------------------------------------------


class GetClusterBackupResponseItem(ProxboxBaseModel):
    """Minimal response from GET /api2/json/cluster/backup - returns job IDs."""

    id: str | None = Field(None, description="The job ID.")


class GetClusterBackupIdResponse(ProxboxLenientModel):
    """
    Full response from GET /api2/json/cluster/backup/{id}.
    Uses lenient model because Proxmox returns many optional fields.
    """

    id: str | None = Field(None, description="The job ID.")
    enabled: bool | None = Field(None, description="Enable or disable the job.")
    node: str | None = Field(None, description="Only run if executed on this node.")
    schedule: str | None = Field(
        None, description="Backup schedule in systemd calendar format."
    )
    starttime: str | None = Field(None, description="Job start time.")
    dow: str | None = Field(None, description="Day of week selection.")
    storage: str | None = Field(
        None, description="Store resulting file to this storage."
    )
    vmid: str | None = Field(None, description="VMIDs selected for backup.")
    all: bool | None = Field(None, description="Backup all known guest systems.")
    exclude: str | None = Field(None, description="Exclude specified guest systems.")
    pool: str | None = Field(None, description="Backup all VMs in this pool.")
    comment: str | None = Field(None, description="Description for the Job.")
    prune_backups: str | None = Field(
        None, alias="prune-backups", description="Retention options string."
    )
    notes_template: str | None = Field(
        None, alias="notes-template", description="Template for backup notes."
    )
    bwlimit: int | None = Field(None, description="I/O bandwidth limit (KiB/s).")
    zstd: int | None = Field(None, description="Zstd threads.")
    pigz: int | None = Field(None, description="pigz threads.")
    ionice: int | None = Field(None, description="IO priority.")
    mode: BackupMode | str | None = Field(None, description="Backup mode.")
    compress: CompressionAlgorithm | str | None = Field(
        None, description="Compression algorithm."
    )
    mailnotification: NotificationMode | str | None = Field(
        None, description="Mail notification mode."
    )
    mailto: str | None = Field(None, description="Comma-separated email addresses.")
    protected: bool | None = Field(None, description="Mark backups as protected.")
    quiet: bool | None = Field(None, description="Be quiet.")
    remove: bool | None = Field(None, description="Prune older backups.")
    fleecing: str | None = Field(None, description="Options for backup fleecing.")
    io_workers: int | None = Field(None, description="IO workers.")
    pbs_change_detection_mode: PBSChangeDetectionMode | str | None = Field(
        None,
        alias="pbs-change-detection-mode",
        description="PBS change detection mode.",
    )
    repeat_missed: bool | None = Field(
        None, alias="repeat-missed", description="Repeat missed job."
    )
    notification_mode: NotificationMode | str | None = Field(
        None, alias="notification-mode", description="Notification mode."
    )
    performance: str | None = Field(None, description="Performance settings.")
    stdexcludes: bool | None = Field(None, description="Exclude temporary files.")
    stop: bool | None = Field(None, description="Stop running backup jobs.")
    stopwait: int | None = Field(None, description="Max wait time to stop guest.")
    lockwait: int | None = Field(None, description="Max wait time for global lock.")
    script: str | None = Field(None, description="Hook script.")
    dumpdir: str | None = Field(None, description="Dump directory.")
    tmpdir: str | None = Field(None, description="Temporary directory.")
    maxfiles: int | None = Field(None, description="Max backup files (deprecated).")

    @field_validator("vmid", mode="before")
    @classmethod
    def _parse_vmid_list(cls, v: str | list | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, list):
            return ",".join(str(x) for x in v)
        return str(v)

    @model_validator(mode="before")
    @classmethod
    def _flatten_id_field(cls, data: dict) -> dict:
        if isinstance(data, dict) and "id" not in data:
            return data
        return data


class BackupRoutineSchema(ProxboxBaseModel):
    """
    Normalized schema for a Proxmox backup routine with parsed retention and computed next_run.
    """

    job_id: str
    enabled: bool = True
    node: str | None = None
    schedule: str | None = None
    next_run: datetime | None = None
    storage: str | None = None
    selection: list[int] = Field(default_factory=list)
    comment: str = ""

    # Retention
    keep_last: int | None = None
    keep_daily: int | None = None
    keep_weekly: int | None = None
    keep_monthly: int | None = None
    keep_yearly: int | None = None
    keep_all: bool | None = None

    # Note template
    notes_template: str | None = None

    # Advanced
    bwlimit: int | None = None
    zstd: int | None = None
    io_workers: int | None = None
    fleecing: str | None = None
    fleecing_storage: str | None = None
    repeat_missed: bool | None = None
    pbs_change_detection_mode: str | None = None

    @classmethod
    def from_proxmox_response(
        cls, data: dict, cluster_name: str | None = None
    ) -> "BackupRoutineSchema":
        """Build a BackupRoutineSchema from a Proxmox API response dict."""
        raw_prune = data.get("prune-backups") or data.get("prune_backups")
        retention = parse_prune_backups(raw_prune)

        # Parse vmid/selection
        vmid_raw = data.get("vmid")
        selection: list[int] = []
        if vmid_raw:
            if isinstance(vmid_raw, str):
                for part in vmid_raw.split(","):
                    part = part.strip()
                    if part.isdigit():
                        selection.append(int(part))
            elif isinstance(vmid_raw, list):
                selection = [int(x) for x in vmid_raw if str(x).isdigit()]

        # Compute next_run from schedule
        schedule = data.get("schedule")
        next_run = None
        if schedule:
            next_run = parse_systemd_calendar_to_datetime(schedule)

        return cls(
            job_id=data.get("id") or "",
            enabled=data.get("enabled", True),
            node=data.get("node"),
            schedule=schedule,
            next_run=next_run,
            storage=data.get("storage"),
            selection=selection,
            comment=data.get("comment") or "",
            keep_last=retention.get("keep_last"),
            keep_daily=retention.get("keep_daily"),
            keep_weekly=retention.get("keep_weekly"),
            keep_monthly=retention.get("keep_monthly"),
            keep_yearly=retention.get("keep_yearly"),
            keep_all=retention.get("keep_all"),
            notes_template=data.get("notes-template") or data.get("notes_template"),
            bwlimit=data.get("bwlimit"),
            zstd=data.get("zstd"),
            io_workers=data.get("io_workers"),
            fleecing=data.get("fleecing"),
            fleecing_storage=data.get("fleecing-storage"),
            repeat_missed=data.get("repeat-missed"),
            pbs_change_detection_mode=data.get("pbs-change-detection-mode"),
        )

    def to_prune_backups_string(self) -> str | None:
        """Serialize retention fields back to a prune-backups string."""
        return format_prune_backups(
            keep_last=self.keep_last,
            keep_daily=self.keep_daily,
            keep_weekly=self.keep_weekly,
            keep_monthly=self.keep_monthly,
            keep_yearly=self.keep_yearly,
            keep_all=self.keep_all,
        )
