"""Choice sets for the netbox-pbs plugin."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from utilities.choices import ChoiceSet


class PBSServerStatusChoices(ChoiceSet):
    """Reachability state for a PBS endpoint."""

    key = "PBSServer.status"

    STATUS_UNKNOWN = "unknown"
    STATUS_REACHABLE = "reachable"
    STATUS_UNREACHABLE = "unreachable"

    CHOICES = [
        (STATUS_UNKNOWN, _("Unknown"), "gray"),
        (STATUS_REACHABLE, _("Reachable"), "green"),
        (STATUS_UNREACHABLE, _("Unreachable"), "red"),
    ]


class PBSJobTypeChoices(ChoiceSet):
    """PBS job families normalized by proxmox-sdk."""

    key = "PBSJob.job_type"

    TYPE_VERIFY = "verify"
    TYPE_PRUNE = "prune"
    TYPE_GC = "gc"
    TYPE_SYNC = "sync"
    TYPE_TAPE = "tape"
    TYPE_UNKNOWN = "unknown"

    CHOICES = [
        (TYPE_VERIFY, _("Verify"), "blue"),
        (TYPE_PRUNE, _("Prune"), "purple"),
        (TYPE_GC, _("Garbage collection"), "orange"),
        (TYPE_SYNC, _("Sync"), "cyan"),
        (TYPE_TAPE, _("Tape"), "indigo"),
        (TYPE_UNKNOWN, _("Unknown"), "gray"),
    ]


class PBSJobRunStateChoices(ChoiceSet):
    """Last-run states returned by PBS job endpoints."""

    key = "PBSJob.last_run_state"

    STATE_OK = "ok"
    STATE_ERROR = "error"
    STATE_WARNING = "warning"
    STATE_RUNNING = "running"
    STATE_UNKNOWN = "unknown"

    CHOICES = [
        (STATE_OK, _("OK"), "green"),
        (STATE_ERROR, _("Error"), "red"),
        (STATE_WARNING, _("Warning"), "yellow"),
        (STATE_RUNNING, _("Running"), "blue"),
        (STATE_UNKNOWN, _("Unknown"), "gray"),
    ]


class PBSGCStatusChoices(ChoiceSet):
    """PBS datastore garbage-collection state."""

    key = "PBSDatastore.gc_status"

    STATUS_OK = "ok"
    STATUS_RUNNING = "running"
    STATUS_ERROR = "error"
    STATUS_PENDING = "pending"
    STATUS_UNKNOWN = "unknown"

    CHOICES = [
        (STATUS_OK, _("OK"), "green"),
        (STATUS_RUNNING, _("Running"), "blue"),
        (STATUS_ERROR, _("Error"), "red"),
        (STATUS_PENDING, _("Pending"), "yellow"),
        (STATUS_UNKNOWN, _("Unknown"), "gray"),
    ]


class PBSBackupTypeChoices(ChoiceSet):
    """PBS backup namespace type."""

    key = "PBSSnapshot.backup_type"

    TYPE_VM = "vm"
    TYPE_CT = "ct"
    TYPE_HOST = "host"
    TYPE_UNKNOWN = "unknown"

    CHOICES = [
        (TYPE_VM, _("Virtual machine"), "blue"),
        (TYPE_CT, _("Container"), "purple"),
        (TYPE_HOST, _("Host"), "green"),
        (TYPE_UNKNOWN, _("Unknown"), "gray"),
    ]
