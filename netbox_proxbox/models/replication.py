"""Define the Replication model for Proxmox storage replication."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel


class Replication(NetBoxModel):
    """Proxmox replication metadata attached to a NetBox VirtualMachine."""

    replication_id = models.CharField(
        max_length=255,
        unique=True,
        help_text=_(
            "Replication job ID. Composed of guest ID and job number: '<GUEST>-<JOBNUM>'."
        ),
    )

    virtual_machine = models.ForeignKey(
        to="virtualization.VirtualMachine",
        on_delete=models.CASCADE,
        related_name="replications",
    )

    proxmox_node = models.ForeignKey(
        to="netbox_proxbox.ProxmoxNode",
        on_delete=models.SET_NULL,
        related_name="replications",
        null=True,
        blank=True,
        help_text=_("Target Proxmox node for replication."),
    )

    guest = models.PositiveIntegerField(help_text=_("Guest ID (VM ID)."))

    target = models.CharField(
        max_length=255,
        help_text=_("Target node for replication."),
    )

    job_type = models.CharField(
        max_length=50,
        choices=[("local", _("Local"))],
        default="local",
        help_text=_("Replication type."),
    )

    schedule = models.CharField(
        max_length=128,
        blank=True,
        help_text=_("Replication schedule (systemd calendar format)."),
    )

    rate = models.FloatField(
        null=True,
        blank=True,
        help_text=_("Rate limit in MB/s."),
    )

    comment = models.TextField(
        null=True,
        blank=True,
        help_text=_("Description of the replication job."),
    )

    disable = models.BooleanField(
        default=False,
        help_text=_("Flag to disable the entry."),
    )

    source = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=_(
            "Source node (for internal use, to detect if the guest was stolen)."
        ),
    )

    jobnum = models.PositiveIntegerField(
        help_text=_("Unique, sequential ID assigned to each job."),
    )

    remove_job = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        choices=[("local", _("Local")), ("full", _("Full"))],
        help_text=_("Mark the replication job for removal."),
    )

    class Meta:
        verbose_name = _("Replication")
        verbose_name_plural = _("Replications")
        ordering = ("virtual_machine", "replication_id")

    def __str__(self) -> str:
        """VM and replication ID for list displays."""
        return f"{self.virtual_machine} - {self.replication_id}"

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this replication's detail page."""
        return reverse("plugins:netbox_proxbox:replication", args=[self.pk])
