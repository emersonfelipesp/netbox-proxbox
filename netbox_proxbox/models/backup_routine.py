"""Define the BackupRoutine model for tracking Proxmox vzdump backup schedules."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel
from netbox.models.features import BackupSyncMixin

from netbox_proxbox.choices import BackupRoutineStatusChoices


class BackupRoutine(NetBoxModel, BackupSyncMixin):
    """
    Tracks a Proxmox vzdump backup schedule (backup routine) synced from a Proxmox endpoint.

    Stores the full job configuration including retention policy, scheduling, and advanced
    options. Routines that no longer exist in Proxmox are marked as stale rather than
    deleted so that historical context is preserved.
    """

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="backup_routines",
        verbose_name=_("Proxmox endpoint"),
        help_text=_("ProxmoxEndpoint this backup routine is discovered from."),
    )
    job_id = models.CharField(
        max_length=255,
        verbose_name=_("Job ID"),
        help_text=_("Unique Proxmox job identifier (e.g. 'local:123')."),
    )
    enabled = models.BooleanField(
        default=True,
        verbose_name=_("Enabled"),
        help_text=_("Whether this backup job is currently enabled."),
    )
    schedule = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Schedule"),
        help_text=_("Systemd calendar format schedule string (e.g. 'daily 04:00')."),
    )
    next_run = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Next Run"),
        help_text=_("Computed next scheduled run time."),
    )
    node = models.ForeignKey(
        to="netbox_proxbox.ProxmoxNode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="backup_routines",
        verbose_name=_("Node"),
        help_text=_("Node to run backup on (null = all nodes)."),
    )
    storage = models.ForeignKey(
        to="netbox_proxbox.ProxmoxStorage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="backup_routines",
        verbose_name=_("Storage"),
        help_text=_("Target storage for backup files."),
    )
    selection = models.JSONField(
        default=list,
        verbose_name=_("Selection"),
        help_text=_("List of VMID values selected for this backup job."),
    )
    comment = models.TextField(
        blank=True,
        verbose_name=_("Comment"),
        help_text=_("Human-readable description or notes for this backup routine."),
    )
    status = models.CharField(
        max_length=20,
        choices=BackupRoutineStatusChoices,
        default=BackupRoutineStatusChoices.ACTIVE,
        verbose_name=_("Status"),
        help_text=_("Active or stale — stale routines no longer exist in Proxmox."),
    )

    # Retention fields
    keep_last = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Keep Last"),
        help_text=_("Number of last backups to retain."),
    )
    keep_daily = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Keep Daily"),
        help_text=_("Number of daily backups to retain."),
    )
    keep_weekly = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Keep Weekly"),
        help_text=_("Number of weekly backups to retain."),
    )
    keep_monthly = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Keep Monthly"),
        help_text=_("Number of monthly backups to retain."),
    )
    keep_yearly = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Keep Yearly"),
        help_text=_("Number of yearly backups to retain."),
    )
    keep_all = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Keep All"),
        help_text=_("Retain all backups regardless of other retention settings."),
    )

    # Note template
    notes_template = models.TextField(
        blank=True,
        verbose_name=_("Notes Template"),
        help_text=_(
            "Template string for generating backup notes. Supports {{cluster}}, {{guestname}}, {{node}}, {{vmid}}."
        ),
    )

    # Advanced fields
    bwlimit = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Bandwidth Limit"),
        help_text=_("I/O bandwidth limit in KiB/s (0 = unlimited)."),
    )
    zstd = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Zstd Threads"),
        help_text=_("Number of zstd compression threads (0 = auto)."),
    )
    io_workers = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("IO Workers"),
        help_text=_("Number of IO workers for parallel processing."),
    )
    fleecing = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Fleecing"),
        help_text=_("Options for backup fleecing (VM only)."),
    )
    fleecing_storage = models.ForeignKey(
        to="netbox_proxbox.ProxmoxStorage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Fleecing Storage"),
        help_text=_("Storage to use for fleecing operations."),
    )
    repeat_missed = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Repeat Missed"),
        help_text=_(
            "Run the job as soon as possible if it was missed while the scheduler was not running."
        ),
    )
    pbs_change_detection_mode = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("PBS Change Detection Mode"),
        help_text=_("PBS mode used to detect file changes for container backups."),
    )

    # Additional raw fields stored as JSON for extensibility
    raw_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Raw Configuration"),
        help_text=_("Full raw configuration from Proxmox API for reference."),
    )

    class Meta:
        ordering = ("endpoint", "job_id")
        verbose_name = _("Backup Routine")
        verbose_name_plural = _("Backup Routines")
        constraints = [
            models.UniqueConstraint(
                fields=["endpoint", "job_id"],
                name="netbox_proxbox_backuproutine_unique_endpoint_job_id",
            )
        ]

    def __str__(self) -> str:
        return f"{self.job_id} ({self.endpoint})"

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this backup routine detail view."""
        return reverse("plugins:netbox_proxbox:backuproutine", args=[self.pk])

    @property
    def selection_display(self) -> str:
        """Human-readable list of selected VMIDs."""
        if not self.selection:
            return "All VMs" if self.raw_config.get("all") else "None"
        selected = ", ".join(str(v) for v in self.selection[:10])
        suffix = (
            f" ... ({len(self.selection)} total)" if len(self.selection) > 10 else ""
        )
        return selected + suffix
