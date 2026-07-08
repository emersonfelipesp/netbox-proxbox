"""Pydantic-friendly enums for Proxmox categorical values used in netbox_proxbox schemas.

These mirror the enums defined in proxbox-api's proxbox_api.enum.proxmox module.
The two repos communicate over HTTP rather than as Python imports, so the definitions
are maintained in both places. Keep the values in sync when updating either side.
"""

from enum import Enum


class BackupMode(str, Enum):
    """vzdump backup mode (controls guest state during backup)."""

    snapshot = "snapshot"
    suspend = "suspend"
    stop = "stop"


class CompressionAlgorithm(str, Enum):
    """Compression algorithm used for backup archives."""

    zstd = "zstd"
    lzo = "lzo"
    gzip = "gzip"
    none = "0"  # Proxmox API uses "0" for no compression


class NotificationMode(str, Enum):
    """When to send backup notification emails."""

    always = "always"
    failure = "failure"
    auto = "auto"
    never = "never"


class PBSChangeDetectionMode(str, Enum):
    """Proxmox Backup Server change detection algorithm."""

    legacy = "legacy"
    data = "data"
    metadata = "metadata"


class ProxmoxVMStatus(str, Enum):
    """Proxmox virtual machine / container runtime status."""

    running = "running"
    stopped = "stopped"
    paused = "paused"
    suspended = "suspended"
    prelaunch = "prelaunch"


class DiskFormat(str, Enum):
    """Disk image / storage content format."""

    qcow2 = "qcow2"
    raw = "raw"
    vmdk = "vmdk"
    subvol = "subvol"
    pbs_vm = "pbs-vm"
    pbs_ct = "pbs-ct"
    zst = "zst"
    tzst = "tzst"
    tgz = "tgz"
    tar = "tar"
    tbz = "tbz"
    iso = "iso"
