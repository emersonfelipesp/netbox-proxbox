"""Define shared choice sets for endpoint, sync, token, and backup fields."""

from django.utils.translation import gettext_lazy as _
from utilities.choices import ChoiceSet


class ProxmoxModeChoices(ChoiceSet):
    key = "ProxmoxEndpoint.mode"

    PROXMOX_MODE_UNDEFINED = "undefined"
    PROXMOX_MODE_STANDALONE = "standalone"
    PROXMOX_MODE_CLUSTER = "cluster"

    CHOICES = [
        (PROXMOX_MODE_UNDEFINED, _("Undefined"), "gray"),
        (PROXMOX_MODE_STANDALONE, _("Standalone"), "blue"),
        (PROXMOX_MODE_CLUSTER, _("Cluster"), "green"),
    ]


class SyncTypeChoices(ChoiceSet):
    key = "SyncProcess.sync_type"

    VIRTUAL_MACHINES = "virtual-machines"
    VIRTUAL_MACHINES_DISKS = "vm-disks"
    VIRTUAL_MACHINES_BACKUPS = "vm-backups"
    DEVICES = "devices"
    ALL = "all"

    CHOICES = [
        (VIRTUAL_MACHINES, _("Virtual Machines"), "blue"),
        (VIRTUAL_MACHINES_DISKS, _("VM Disks"), "orange"),
        (VIRTUAL_MACHINES_BACKUPS, _("Virtual Machines Backups"), "purple"),
        (DEVICES, _("Devices"), "green"),
        (ALL, _("All"), "red"),
    ]


class SyncStatusChoices(ChoiceSet):
    key = "SyncProcess.status"

    NOT_STARTED = "not-started"
    SYNCING = "syncing"
    COMPLETED = "completed"
    FAILED = "failed"

    CHOICES = [
        (NOT_STARTED, _("Not Started"), "gray"),
        (SYNCING, _("Syncing"), "blue"),
        (COMPLETED, _("Completed"), "green"),
        (FAILED, _("Failed"), "red"),
    ]


class NetBoxTokenVersionChoices(ChoiceSet):
    key = "NetBoxEndpoint.token_version"

    V1 = "v1"
    V2 = "v2"

    CHOICES = [
        (V1, _("v1 Token"), "blue"),
        (V2, _("v2 Token"), "green"),
    ]


class ProxmoxBackupSubtypeChoices(ChoiceSet):
    key = "VMBackup.subtype"

    BACKUP_SUBTYPE_UNDEFINED = "undefined"
    BACKUP_SUBTYPE_LXC = "lxc"
    BACKUP_SUBTYPE_QEMU = "qemu"

    CHOICES = [
        (BACKUP_SUBTYPE_UNDEFINED, _("Undefined"), "gray"),
        (BACKUP_SUBTYPE_LXC, _("LXC"), "blue"),
        (BACKUP_SUBTYPE_QEMU, _("QEMU"), "green"),
    ]


class ProxmoxBackupFormatChoices(ChoiceSet):
    key = "VMBackup.format"

    BACKUP_FORMAT_UNDEFINED = "undefined"
    BACKUP_FORMAT_PBS_VM = "pbs-vm"
    BACKUP_FORMAT_PBS_CT = "pbs-ct"
    BACKUP_FORMAT_ISO = "iso"
    BACKUP_FORMAT_TZST = "tzst"
    BACKUP_FORMAT_TGZ = "tgz"
    BACKUP_FORMAT_QCOW2 = "qcow2"
    BACKUP_FORMAT_RAW = "raw"
    BACKUP_FORMAT_TAR = "tar"
    BACKUP_FORMAT_TBZ = "tbz"

    CHOICES = [
        (BACKUP_FORMAT_UNDEFINED, _("Undefined"), "gray"),
        (BACKUP_FORMAT_PBS_VM, _("PBS VM"), "blue"),
        (BACKUP_FORMAT_PBS_CT, _("PBS CT"), "green"),
        (BACKUP_FORMAT_ISO, _("ISO"), "yellow"),
        (BACKUP_FORMAT_TZST, _("TZST"), "purple"),
        (BACKUP_FORMAT_TGZ, _("TGZ"), "red"),
        (BACKUP_FORMAT_QCOW2, _("QCOW2"), "orange"),
        (BACKUP_FORMAT_RAW, _("RAW"), "pink"),
        (BACKUP_FORMAT_TAR, _("TAR"), "brown"),
        (BACKUP_FORMAT_TBZ, _("TBZ"), "gray"),
    ]


class ProxmoxSnapshotSubtypeChoices(ChoiceSet):
    key = "VMSnapshot.subtype"

    SNAPSHOT_SUBTYPE_QEMU = "qemu"
    SNAPSHOT_SUBTYPE_LXC = "lxc"

    CHOICES = [
        (SNAPSHOT_SUBTYPE_QEMU, _("QEMU"), "green"),
        (SNAPSHOT_SUBTYPE_LXC, _("LXC"), "blue"),
    ]


class ProxmoxSnapshotStatusChoices(ChoiceSet):
    key = "VMSnapshot.status"

    SNAPSHOT_STATUS_ACTIVE = "active"
    SNAPSHOT_STATUS_STALE = "stale"

    CHOICES = [
        (SNAPSHOT_STATUS_ACTIVE, _("Active"), "green"),
        (SNAPSHOT_STATUS_STALE, _("Stale"), "red"),
    ]


class ScheduleIntervalUnitChoices(ChoiceSet):
    key = "ScheduleSync.interval_unit"

    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"

    CHOICES = [
        (MINUTES, _("Minutes"), "blue"),
        (HOURS, _("Hours"), "green"),
        (DAYS, _("Days"), "yellow"),
        (WEEKS, _("Weeks"), "purple"),
    ]

    MINUTE_MULTIPLIERS = {
        MINUTES: 1,
        HOURS: 60,
        DAYS: 60 * 24,
        WEEKS: 60 * 24 * 7,
    }

    @classmethod
    def to_minutes(cls, value: int, unit: str) -> int:
        multiplier = cls.MINUTE_MULTIPLIERS.get(unit, 1)
        return value * multiplier

    @classmethod
    def from_minutes(cls, minutes: int) -> tuple[int, str]:
        if minutes >= 60 * 24 * 7 and minutes % (60 * 24 * 7) == 0:
            return minutes // (60 * 24 * 7), cls.WEEKS
        elif minutes >= 60 * 24 and minutes % (60 * 24) == 0:
            return minutes // (60 * 24), cls.DAYS
        elif minutes >= 60 and minutes % 60 == 0:
            return minutes // 60, cls.HOURS
        return minutes, cls.MINUTES
