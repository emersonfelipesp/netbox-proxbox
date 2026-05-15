"""``ProxmoxApplyJob`` model for the NetBox→Proxmox intent path."""

from __future__ import annotations

import logging
import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel

logger = logging.getLogger(__name__)


class ProxmoxApplyJob(NetBoxModel):
    """Records a single NetBox→Proxmox apply run triggered by a branch merge.

    Sub-PR E keeps the executor dry-run only: rows record the merge intent and
    per-VM stub results, but no Proxmox-side mutation is dispatched from here.
    """

    class State(models.TextChoices):
        queued = "queued", _("Queued")
        running = "running", _("Running")
        succeeded = "succeeded", _("Succeeded")
        failed = "failed", _("Failed")
        partial = "partial", _("Partial")

    name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Name"),
        help_text=_("Optional human-readable label for the apply run."),
    )
    branch_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_("Branch ID"),
        help_text=_(
            "Primary key of the merged netbox-branching Branch that triggered this run."
        ),
    )
    branch_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Branch name"),
        help_text=_("Name of the merged netbox-branching Branch at queue time."),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
        verbose_name=_("User"),
        help_text=_("User associated with the branch merge that queued this run."),
    )
    run_uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("Run UUID"),
        help_text=_("Stable run identifier shared with proxbox-api apply logs."),
    )
    state = models.CharField(
        max_length=32,
        choices=State.choices,
        default=State.queued,
        verbose_name=_("State"),
        help_text=_("Current dry-run executor state."),
    )
    per_vm_results = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Per-VM results"),
        help_text=_("Dry-run result stubs keyed by VM identifier."),
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Started at"),
    )
    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Finished at"),
    )

    class Meta:
        ordering = ("-pk",)
        verbose_name = _("Proxmox Apply Job")
        verbose_name_plural = _("Proxmox Apply Jobs")
        permissions = (
            ("intent_create_vm", "Can request CREATE of a Proxmox QEMU VM via intent"),
            ("intent_update_vm", "Can request UPDATE of a Proxmox QEMU VM via intent"),
            ("intent_delete_vm", "Can request DELETE of a Proxmox QEMU VM via intent"),
            (
                "intent_create_lxc",
                "Can request CREATE of a Proxmox LXC container via intent",
            ),
            (
                "intent_update_lxc",
                "Can request UPDATE of a Proxmox LXC container via intent",
            ),
            (
                "intent_delete_lxc",
                "Can request DELETE of a Proxmox LXC container via intent",
            ),
        )

    def __str__(self) -> str:
        return self.name or f"ProxmoxApplyJob #{self.pk}"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_proxbox:proxmoxapplyjob", args=[self.pk])

    @property
    def branch(self):
        """Resolve the underlying netbox-branching Branch lazily, if installed."""
        if not self.branch_id:
            return None
        try:
            from netbox_branching.models import Branch  # noqa: PLC0415
        except ImportError:
            return None
        return Branch.objects.filter(pk=self.branch_id).first()
