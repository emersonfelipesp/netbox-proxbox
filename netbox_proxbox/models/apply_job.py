"""Shell ``ProxmoxApplyJob`` model for the NetBox→Proxmox intent path.

Sub-PR B introduces only the minimal field set required to register the model
with the seven intent RBAC permissions in migration 0038. The full schema (FK
to branch + user, ``run_uuid``, ``state``, ``per_vm_results``, timestamps) lands
in Sub-PR E (``0040_apply_job_full``).
"""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel


class ProxmoxApplyJob(NetBoxModel):
    """Records a single NetBox→Proxmox apply run triggered by a branch merge.

    Promoted to its full schema in Sub-PR E (migration ``0040_apply_job_full``).
    The shell exists now so the seven intent permissions in migration
    ``0038_intent_permissions`` can attach to a real ContentType and so the
    apply-job views/templates added in Sub-PR E can register against a stable
    model path.
    """

    name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Name"),
        help_text=_("Optional human-readable label for the apply run."),
    )

    class Meta:
        ordering = ("-pk",)
        verbose_name = _("Proxmox Apply Job")
        verbose_name_plural = _("Proxmox Apply Jobs")
        permissions = (
            ("intent_create_vm", "Can request CREATE of a Proxmox QEMU VM via intent"),
            ("intent_update_vm", "Can request UPDATE of a Proxmox QEMU VM via intent"),
            ("intent_delete_vm", "Can request DELETE of a Proxmox QEMU VM via intent"),
            ("intent_create_lxc", "Can request CREATE of a Proxmox LXC container via intent"),
            ("intent_update_lxc", "Can request UPDATE of a Proxmox LXC container via intent"),
            ("intent_delete_lxc", "Can request DELETE of a Proxmox LXC container via intent"),
        )

    def __str__(self) -> str:
        return self.name or f"ProxmoxApplyJob #{self.pk}"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_proxbox:proxmoxapplyjob", args=[self.pk])
