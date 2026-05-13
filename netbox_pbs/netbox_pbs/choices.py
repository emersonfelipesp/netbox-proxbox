"""Shared choice sets for netbox-pbs domain models."""

from django.utils.translation import gettext_lazy as _
from utilities.choices import ChoiceSet


class PBSBackupTypeChoices(ChoiceSet):
    """Proxmox Backup Server group type."""

    key = "PBSBackupGroup.backup_type"

    BACKUP_TYPE_VM = "vm"
    BACKUP_TYPE_CT = "ct"
    BACKUP_TYPE_HOST = "host"

    CHOICES = [
        (BACKUP_TYPE_VM, _("VM (QEMU)"), "blue"),
        (BACKUP_TYPE_CT, _("Container (LXC)"), "cyan"),
        (BACKUP_TYPE_HOST, _("Host"), "gray"),
    ]


class PBSSnapshotVerifyChoices(ChoiceSet):
    """Verification state for a PBS snapshot."""

    key = "PBSSnapshot.verified"

    VERIFY_NONE = "none"
    VERIFY_OK = "ok"
    VERIFY_FAILED = "failed"

    CHOICES = [
        (VERIFY_NONE, _("Not verified"), "gray"),
        (VERIFY_OK, _("OK"), "green"),
        (VERIFY_FAILED, _("Failed"), "red"),
    ]


class PBSJobTypeChoices(ChoiceSet):
    """PBS job kind reported by /admin/{verify,prune,gc,sync,tape}-job."""

    key = "PBSJobStatus.job_type"

    JOB_TYPE_VERIFY = "verify"
    JOB_TYPE_PRUNE = "prune"
    JOB_TYPE_GC = "gc"
    JOB_TYPE_SYNC = "sync"
    JOB_TYPE_TAPE = "tape"

    CHOICES = [
        (JOB_TYPE_VERIFY, _("Verify"), "blue"),
        (JOB_TYPE_PRUNE, _("Prune"), "orange"),
        (JOB_TYPE_GC, _("Garbage collection"), "purple"),
        (JOB_TYPE_SYNC, _("Sync"), "cyan"),
        (JOB_TYPE_TAPE, _("Tape"), "gray"),
    ]


class PBSJobRunStateChoices(ChoiceSet):
    """Terminal state reported for the last run of a PBS job."""

    key = "PBSJobStatus.last_run_state"

    RUN_STATE_UNKNOWN = "unknown"
    RUN_STATE_OK = "ok"
    RUN_STATE_WARNING = "warning"
    RUN_STATE_ERROR = "error"

    CHOICES = [
        (RUN_STATE_UNKNOWN, _("Unknown"), "gray"),
        (RUN_STATE_OK, _("OK"), "green"),
        (RUN_STATE_WARNING, _("Warning"), "yellow"),
        (RUN_STATE_ERROR, _("Error"), "red"),
    ]


class PBSDatastoreGCStatusChoices(ChoiceSet):
    """Last-known garbage-collection status reported by a PBS datastore."""

    key = "PBSDatastore.gc_status"

    GC_STATUS_UNKNOWN = "unknown"
    GC_STATUS_IDLE = "idle"
    GC_STATUS_RUNNING = "running"
    GC_STATUS_OK = "ok"
    GC_STATUS_ERROR = "error"

    CHOICES = [
        (GC_STATUS_UNKNOWN, _("Unknown"), "gray"),
        (GC_STATUS_IDLE, _("Idle"), "gray"),
        (GC_STATUS_RUNNING, _("Running"), "blue"),
        (GC_STATUS_OK, _("OK"), "green"),
        (GC_STATUS_ERROR, _("Error"), "red"),
    ]
