"""Cloud image templates exposed to Cloud Portal tenants for VM provisioning."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel

from netbox_proxbox.choices import CloudImageOSFamilyChoices


class CloudImageTemplate(NetBoxModel):
    """Catalog entry mapping a tenant-visible cloud image to a Proxmox VM template."""

    name = models.CharField(
        max_length=255,
        verbose_name=_("Name"),
        help_text=_("Human-readable cloud image template name."),
    )
    slug = models.SlugField(
        max_length=255,
        unique=True,
        verbose_name=_("Slug"),
        help_text=_("Unique slug used by API clients and automation."),
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Optional operator-facing description for this cloud image."),
    )
    cluster = models.ForeignKey(
        to="virtualization.Cluster",
        on_delete=models.CASCADE,
        related_name="proxbox_cloud_image_templates",
        verbose_name=_("Cluster"),
        help_text=_("NetBox cluster that contains the Proxmox source template VMID."),
    )
    source_vmid = models.PositiveIntegerField(
        verbose_name=_("Source VMID"),
        help_text=_("Proxmox VMID of the source cloud-image template."),
    )
    os_family = models.CharField(
        max_length=32,
        choices=CloudImageOSFamilyChoices,
        default=CloudImageOSFamilyChoices.GENERIC,
        verbose_name=_("OS family"),
        help_text=_("Operating-system family represented by this image."),
    )
    os_release = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("OS release"),
        help_text=_("Optional OS release or codename, for example jammy."),
    )
    default_ciuser = models.CharField(
        max_length=64,
        default="cloud-user",
        verbose_name=_("Default cloud-init user"),
        help_text=_("Default ciuser value supplied when provisioning from this image."),
    )
    allowed_tenants = models.ManyToManyField(
        to="tenancy.Tenant",
        blank=True,
        related_name="proxbox_cloud_image_templates",
        verbose_name=_("Allowed tenants"),
        help_text=_("Tenants allowed to use this image. Leave empty for all tenants."),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_("Inactive templates are hidden from tenant provisioning flows."),
    )

    class Meta:
        ordering = ("cluster", "name", "source_vmid")
        unique_together = ("cluster", "source_vmid")
        verbose_name = _("Cloud image template")
        verbose_name_plural = _("Cloud image templates")
        permissions = [
            (
                "provision_cloud_vm",
                _("Can provision a VM from a cloud image template"),
            ),
        ]

    def __str__(self) -> str:
        release = f" {self.os_release}" if self.os_release else ""
        return f"{self.name} ({self.os_family}{release})"

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this cloud image template detail view."""
        return reverse("plugins:netbox_proxbox:cloudimagetemplate", args=[self.pk])

    @property
    def tenant_scope_label(self) -> str:
        """Readable scope for templates where an empty tenant set means all tenants."""
        if not getattr(self, "pk", None):
            return "All tenants"
        tenants = list(self.allowed_tenants.all()[:4])
        if not tenants:
            return "All tenants"
        names = ", ".join(str(tenant) for tenant in tenants)
        total = self.allowed_tenants.count()
        return f"{names} (+{total - 4} more)" if total > 4 else names
