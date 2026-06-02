"""Define shared choice sets for endpoint, sync, token, and backup fields."""

from django.utils.translation import gettext_lazy as _
from utilities.choices import ChoiceSet


class ProxmoxModeChoices(ChoiceSet):
    """Proxmox VE deployment mode (standalone vs cluster)."""

    key = "ProxmoxEndpoint.mode"

    PROXMOX_MODE_UNDEFINED = "undefined"
    PROXMOX_MODE_STANDALONE = "standalone"
    PROXMOX_MODE_CLUSTER = "cluster"

    CHOICES = [
        (PROXMOX_MODE_UNDEFINED, _("Undefined"), "gray"),
        (PROXMOX_MODE_STANDALONE, _("Standalone"), "blue"),
        (PROXMOX_MODE_CLUSTER, _("Cluster"), "green"),
    ]


class ProxmoxEndpointEnvironmentChoices(ChoiceSet):
    """Operator-selected lifecycle stage for a Proxmox endpoint.

    Manual classification only; never written by sync. Blank is a valid value.
    """

    key = "ProxmoxEndpoint.environment"

    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"
    HOMOLOGATION = "homologation"
    TESTING = "testing"
    LAB = "lab"

    CHOICES = [
        (PRODUCTION, _("Production"), "red"),
        (STAGING, _("Staging"), "orange"),
        (DEVELOPMENT, _("Development"), "blue"),
        (HOMOLOGATION, _("Homologation"), "purple"),
        (TESTING, _("Testing"), "yellow"),
        (LAB, _("Lab"), "gray"),
    ]


class SyncTypeChoices(ChoiceSet):
    """Which ProxBox sync operation to run (devices, VMs, backups, full, etc.)."""

    key = "ProxboxSync.sync_type"

    VIRTUAL_MACHINES = "virtual-machines"
    STORAGE = "storage"
    VIRTUAL_MACHINES_DISKS = "vm-disks"
    VIRTUAL_MACHINES_BACKUPS = "vm-backups"
    VIRTUAL_MACHINES_SNAPSHOTS = "vm-snapshots"
    DEVICES = "devices"
    NETWORK_INTERFACES = "network-interfaces"
    VM_INTERFACES = "vm-interfaces"
    IP_ADDRESSES = "ip-addresses"
    BACKUP_ROUTINES = "backup-routines"
    REPLICATIONS = "replications"
    TASK_HISTORY = "task-history"
    ALL = "all"

    CHOICES = [
        (VIRTUAL_MACHINES, _("Virtual Machines"), "blue"),
        (STORAGE, _("Storage"), "teal"),
        (VIRTUAL_MACHINES_DISKS, _("VM Disks"), "orange"),
        (VIRTUAL_MACHINES_BACKUPS, _("Virtual Machines Backups"), "purple"),
        (VIRTUAL_MACHINES_SNAPSHOTS, _("VM Snapshots"), "cyan"),
        (DEVICES, _("Devices"), "green"),
        (NETWORK_INTERFACES, _("Network Interfaces"), "indigo"),
        (VM_INTERFACES, _("VM Interfaces"), "indigo"),
        (IP_ADDRESSES, _("IP Addresses"), "violet"),
        (BACKUP_ROUTINES, _("Backup Routines"), "yellow"),
        (REPLICATIONS, _("Replications"), "teal"),
        (TASK_HISTORY, _("Task History"), "amber"),
        (ALL, _("All"), "red"),
    ]


class SyncModeChoices(ChoiceSet):
    """Per-resource sync behavior for reflected Proxmox inventory."""

    key = "ProxboxPluginSettings.sync_mode"

    ALWAYS = "always"
    BOOTSTRAP_ONLY = "bootstrap_only"
    DISABLED = "disabled"

    CHOICES = [
        (ALWAYS, _("Always"), "green"),
        (BOOTSTRAP_ONLY, _("Bootstrap only"), "yellow"),
        (DISABLED, _("Disabled"), "red"),
    ]


class NetBoxTokenVersionChoices(ChoiceSet):
    """NetBox REST API token style for remote endpoint authentication."""

    key = "NetBoxEndpoint.token_version"

    V1 = "v1"
    V2 = "v2"

    CHOICES = [
        (V1, _("v1 Token"), "blue"),
        (V2, _("v2 Token"), "green"),
    ]


class ProxmoxBackupSubtypeChoices(ChoiceSet):
    """Hypervisor subtype for a VM backup row (QEMU vs LXC)."""

    key = "VMBackup.subtype"

    BACKUP_SUBTYPE_UNDEFINED = "undefined"
    BACKUP_SUBTYPE_LXC = "lxc"
    BACKUP_SUBTYPE_CT = "ct"
    BACKUP_SUBTYPE_QEMU = "qemu"
    BACKUP_SUBTYPE_VM = "vm"

    CHOICES = [
        (BACKUP_SUBTYPE_UNDEFINED, _("Undefined"), "gray"),
        (BACKUP_SUBTYPE_LXC, _("LXC"), "blue"),
        (BACKUP_SUBTYPE_CT, _("CT"), "blue"),
        (BACKUP_SUBTYPE_QEMU, _("QEMU"), "green"),
        (BACKUP_SUBTYPE_VM, _("VM"), "green"),
    ]


class ProxmoxBackupFormatChoices(ChoiceSet):
    """Backup image or archive format as reported by Proxmox."""

    key = "VMBackup.format"

    BACKUP_FORMAT_UNDEFINED = "undefined"
    BACKUP_FORMAT_PBS_VM = "pbs-vm"
    BACKUP_FORMAT_PBS_CT = "pbs-ct"
    BACKUP_FORMAT_ZST = "zst"
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
        (BACKUP_FORMAT_ZST, _("ZST"), "purple"),
        (BACKUP_FORMAT_ISO, _("ISO"), "yellow"),
        (BACKUP_FORMAT_TZST, _("TZST"), "purple"),
        (BACKUP_FORMAT_TGZ, _("TGZ"), "red"),
        (BACKUP_FORMAT_QCOW2, _("QCOW2"), "orange"),
        (BACKUP_FORMAT_RAW, _("RAW"), "pink"),
        (BACKUP_FORMAT_TAR, _("TAR"), "brown"),
        (BACKUP_FORMAT_TBZ, _("TBZ"), "gray"),
    ]


class ProxmoxSnapshotSubtypeChoices(ChoiceSet):
    """Hypervisor subtype for a VM snapshot (QEMU vs LXC)."""

    key = "VMSnapshot.subtype"

    SNAPSHOT_SUBTYPE_QEMU = "qemu"
    SNAPSHOT_SUBTYPE_LXC = "lxc"

    CHOICES = [
        (SNAPSHOT_SUBTYPE_QEMU, _("QEMU"), "green"),
        (SNAPSHOT_SUBTYPE_LXC, _("LXC"), "blue"),
    ]


class ProxmoxSnapshotStatusChoices(ChoiceSet):
    """Whether a snapshot is considered current or stale."""

    key = "VMSnapshot.status"

    SNAPSHOT_STATUS_ACTIVE = "active"
    SNAPSHOT_STATUS_STALE = "stale"

    CHOICES = [
        (SNAPSHOT_STATUS_ACTIVE, _("Active"), "green"),
        (SNAPSHOT_STATUS_STALE, _("Stale"), "red"),
    ]


class ScheduleIntervalUnitChoices(ChoiceSet):
    """Time unit for recurring ProxBox sync schedules (converted to minutes for jobs)."""

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
        """Convert an interval value and unit to total minutes."""
        multiplier = cls.MINUTE_MULTIPLIERS.get(unit, 1)
        return value * multiplier

    @classmethod
    def from_minutes(cls, minutes: int) -> tuple[int, str]:
        """Pick the largest whole unit (weeks down to minutes) for a minute count."""
        if minutes >= 60 * 24 * 7 and minutes % (60 * 24 * 7) == 0:
            return minutes // (60 * 24 * 7), cls.WEEKS
        elif minutes >= 60 * 24 and minutes % (60 * 24) == 0:
            return minutes // (60 * 24), cls.DAYS
        elif minutes >= 60 and minutes % 60 == 0:
            return minutes // 60, cls.HOURS
        return minutes, cls.MINUTES


class BackupRoutineStatusChoices(ChoiceSet):
    """Whether a backup routine is currently active or stale (no longer exists in Proxmox)."""

    key = "BackupRoutine.status"

    ACTIVE = "active"
    STALE = "stale"

    CHOICES = [
        (ACTIVE, _("Active"), "green"),
        (STALE, _("Stale"), "red"),
    ]


class ReplicationJobTypeChoices(ChoiceSet):
    """Proxmox replication job type (section type)."""

    key = "Replication.job_type"

    LOCAL = "local"

    CHOICES = [
        (LOCAL, _("Local"), "blue"),
    ]


class ReplicationRemoveJobChoices(ChoiceSet):
    """Mark a Proxmox replication job for removal."""

    key = "Replication.remove_job"

    LOCAL = "local"
    FULL = "full"

    CHOICES = [
        (LOCAL, _("Local"), "yellow"),
        (FULL, _("Full"), "red"),
    ]


class ReplicationStatusChoices(ChoiceSet):
    """Whether a replication job is currently active or stale (no longer exists in Proxmox)."""

    key = "Replication.status"

    ACTIVE = "active"
    STALE = "stale"

    CHOICES = [
        (ACTIVE, _("Active"), "green"),
        (STALE, _("Stale"), "red"),
    ]


class CloudImageOSFamilyChoices(ChoiceSet):
    """Operating-system families exposed through the cloud image catalog."""

    key = "CloudImageTemplate.os_family"

    UBUNTU = "ubuntu"
    DEBIAN = "debian"
    ROCKY = "rocky"
    ALPINE = "alpine"
    GENERIC = "generic"
    PROXMOX_PBS = "proxmox-pbs"
    PROXMOX_PDM = "proxmox-pdm"
    PFSENSE = "pfsense"
    OPNSENSE = "opnsense"

    CHOICES = [
        (UBUNTU, _("Ubuntu"), "orange"),
        (DEBIAN, _("Debian"), "red"),
        (ROCKY, _("Rocky Linux"), "green"),
        (ALPINE, _("Alpine Linux"), "blue"),
        (GENERIC, _("Generic Linux"), "gray"),
        (PROXMOX_PBS, _("Proxmox Backup Server"), "purple"),
        (PROXMOX_PDM, _("Proxmox Datacenter Manager"), "cyan"),
        (PFSENSE, _("pfSense"), "red"),
        (OPNSENSE, _("OPNsense"), "orange"),
    ]


class FirecrackerHostStatusChoices(ChoiceSet):
    """Operational status for a Firecracker host-agent VM."""

    key = "FirecrackerHost.status"

    READY = "ready"
    DRAINING = "draining"
    OFFLINE = "offline"
    ERROR = "error"

    CHOICES = [
        (READY, _("Ready"), "green"),
        (DRAINING, _("Draining"), "orange"),
        (OFFLINE, _("Offline"), "gray"),
        (ERROR, _("Error"), "red"),
    ]


class FirecrackerMicroVMStatusChoices(ChoiceSet):
    """Lifecycle status for a Firecracker micro-VM."""

    key = "FirecrackerMicroVM.status"

    PROVISIONING = "provisioning"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    DELETED = "deleted"

    CHOICES = [
        (PROVISIONING, _("Provisioning"), "blue"),
        (RUNNING, _("Running"), "green"),
        (STOPPED, _("Stopped"), "gray"),
        (ERROR, _("Error"), "red"),
        (DELETED, _("Deleted"), "black"),
    ]


class FirecrackerNetworkModeChoices(ChoiceSet):
    """Network attachment mode requested for a Firecracker micro-VM."""

    key = "Firecracker.network_mode"

    NAT = "nat"
    BRIDGE = "bridge"

    CHOICES = [
        (NAT, _("NAT"), "blue"),
        (BRIDGE, _("Bridge"), "green"),
    ]


class ProxmoxVMTypeChoices(ChoiceSet):
    """Proxmox hypervisor VM type (QEMU vs LXC) as stored in the proxmox_vm_type custom field."""

    key = "VirtualMachine.proxmox_vm_type"

    QEMU = "qemu"
    LXC = "lxc"

    CHOICES = [
        (QEMU, _("QEMU"), "green"),
        (LXC, _("LXC"), "blue"),
    ]


class FirewallSyncStatusChoices(ChoiceSet):
    """Active or stale sync state for firewall objects."""

    key = "FirewallSync.status"
    ACTIVE = "active"
    STALE = "stale"
    ERROR = "error"
    CHOICES = [
        (ACTIVE, _("Active"), "green"),
        (STALE, _("Stale"), "orange"),
        (ERROR, _("Error"), "red"),
    ]


class FirewallZoneChoices(ChoiceSet):
    """Proxmox firewall zone/level."""

    key = "FirewallRule.zone"
    DATACENTER = "datacenter"
    NODE = "node"
    VM_QEMU = "vm_qemu"
    VM_LXC = "vm_lxc"
    SECURITY_GROUP = "security_group"
    VNET = "vnet"
    CHOICES = [
        (DATACENTER, _("Datacenter"), "blue"),
        (NODE, _("Node"), "cyan"),
        (VM_QEMU, _("VM (QEMU)"), "green"),
        (VM_LXC, _("CT (LXC)"), "teal"),
        (SECURITY_GROUP, _("Security Group"), "purple"),
        (VNET, _("VNet (SDN)"), "gray"),
    ]


class FirewallScopeChoices(ChoiceSet):
    """Scope for firewall IPSets and Aliases."""

    key = "FirewallIPSet.scope"
    DATACENTER = "datacenter"
    VM_QEMU = "vm_qemu"
    VM_LXC = "vm_lxc"
    CHOICES = [
        (DATACENTER, _("Datacenter"), "blue"),
        (VM_QEMU, _("VM (QEMU)"), "green"),
        (VM_LXC, _("CT (LXC)"), "teal"),
    ]


class FirewallRuleTypeChoices(ChoiceSet):
    """Firewall rule direction type."""

    key = "FirewallRule.rule_type"
    IN = "in"
    OUT = "out"
    FORWARD = "forward"
    GROUP = "group"
    CHOICES = [
        (IN, _("In"), "green"),
        (OUT, _("Out"), "red"),
        (FORWARD, _("Forward"), "blue"),
        (GROUP, _("Group"), "purple"),
    ]


class FirewallLogLevelChoices(ChoiceSet):
    """Firewall rule log level."""

    key = "FirewallRule.log"
    NOLOG = "nolog"
    EMERG = "emerg"
    ALERT = "alert"
    CRIT = "crit"
    ERR = "err"
    WARNING = "warning"
    NOTICE = "notice"
    INFO = "info"
    DEBUG = "debug"
    CHOICES = [
        (NOLOG, _("No Log"), "gray"),
        (EMERG, _("Emergency"), "red"),
        (ALERT, _("Alert"), "red"),
        (CRIT, _("Critical"), "red"),
        (ERR, _("Error"), "orange"),
        (WARNING, _("Warning"), "yellow"),
        (NOTICE, _("Notice"), "blue"),
        (INFO, _("Info"), "cyan"),
        (DEBUG, _("Debug"), "gray"),
    ]


class SdnFabricTypeChoices(ChoiceSet):
    """Proxmox SDN fabric type."""

    key = "ProxmoxSdnFabric.fabric_type"
    WIREGUARD = "wireguard"
    BGP = "bgp"
    VXLAN = "vxlan"
    OSPF = "ospf"
    CHOICES = [
        (WIREGUARD, _("WireGuard"), "purple"),
        (BGP, _("BGP"), "blue"),
        (VXLAN, _("VXLAN"), "cyan"),
        (OSPF, _("OSPF"), "green"),
    ]
