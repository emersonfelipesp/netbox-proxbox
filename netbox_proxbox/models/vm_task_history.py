"""Define Proxmox task history rows stored alongside NetBox virtual machines."""

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel

DEFAULT_VM_TYPE = "unknown"


class VMTaskHistory(NetBoxModel):
    """Archived Proxmox task metadata attached to a NetBox ``VirtualMachine``."""

    virtual_machine = models.ForeignKey(
        to="virtualization.VirtualMachine",
        on_delete=models.CASCADE,
        related_name="task_histories",
    )

    vm_type = models.CharField(
        max_length=16,
        default=DEFAULT_VM_TYPE,
        help_text=_("Proxmox guest type, such as qemu or lxc."),
    )

    upid = models.CharField(
        max_length=255,
        unique=True,
        help_text=_("Proxmox task UPID."),
    )

    node = models.CharField(
        max_length=255,
        help_text=_("Proxmox node name."),
    )

    pid = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Process ID for the Proxmox task."),
    )

    pstart = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Process start time for the Proxmox task."),
    )

    task_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Task target identifier from Proxmox."),
    )

    task_type = models.CharField(
        max_length=255,
        help_text=_("Proxmox task type."),
    )

    username = models.CharField(
        max_length=255,
        help_text=_("User who triggered the Proxmox task."),
    )

    start_time = models.DateTimeField(
        help_text=_("Task start time."),
    )

    end_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Task end time."),
    )

    description = models.TextField(
        help_text=_("Human-readable task description."),
    )

    status = models.CharField(
        max_length=255,
        help_text=_("Task outcome or current state."),
    )

    task_state = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Raw Proxmox task state."),
    )

    exitstatus = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Raw Proxmox task exit status."),
    )

    class Meta:
        verbose_name = "VM Task History"
        verbose_name_plural = "VM Task Histories"
        ordering = ("-start_time", "virtual_machine", "node")

    def __str__(self) -> str:
        """VM and task description for list displays."""
        return f"{self.virtual_machine} - {self.description}"

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this task history row."""
        return reverse("plugins:netbox_proxbox:vmtaskhistory", args=[self.pk])
