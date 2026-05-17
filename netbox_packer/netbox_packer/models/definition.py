"""Packer image definition model."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel
from utilities.json import CustomFieldJSONEncoder

from netbox_packer.choices import (
    PackerBuilderTypeChoices,
    PackerOSFamilyChoices,
    PackerProvisionerRecipeChoices,
)


class PackerImageDefinition(NetBoxModel):
    """Reusable recipe for a Proxmox VM image build.

    ``target_cluster`` remains nullable for non-publishing future builders, but
    PHASE2 rejects ``proxmox-clone`` definitions without a cluster because
    PHASE5 publishes successful builds into ``CloudImageTemplate``, whose
    ``cluster`` field is non-nullable. PHASE5 will enforce the same rule on
    the server-side build action before dispatching proxbox-api work.
    """

    name = models.CharField(max_length=255, unique=True, verbose_name=_("Name"))
    slug = models.SlugField(max_length=255, verbose_name=_("Slug"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    enabled = models.BooleanField(default=True, verbose_name=_("Enabled"))
    builder_type = models.CharField(
        max_length=32,
        choices=PackerBuilderTypeChoices,
        default=PackerBuilderTypeChoices.PROXMOX_CLONE,
        verbose_name=_("Builder type"),
    )
    proxmox_endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.PROTECT,
        related_name="packer_image_definitions",
        verbose_name=_("Proxmox endpoint"),
    )
    target_cluster = models.ForeignKey(
        to="virtualization.Cluster",
        on_delete=models.PROTECT,
        related_name="packer_image_definitions",
        null=True,
        blank=True,
        verbose_name=_("Target cluster"),
    )
    target_node = models.CharField(max_length=255, verbose_name=_("Target node"))
    source_template_vmid = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Source template VMID"),
        help_text=_("Required for proxmox-clone builder type."),
    )
    iso_url = models.URLField(
        max_length=512,
        blank=True,
        verbose_name=_("ISO URL"),
        help_text=_("Direct URL of the ISO image (proxmox-iso builder only)."),
    )
    iso_checksum = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("ISO checksum"),
        help_text=_("SHA-256 checksum prefixed with 'sha256:' (proxmox-iso builder only)."),
    )
    iso_storage = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("ISO storage reference"),
        help_text=_(
            "Proxmox storage reference for a pre-uploaded ISO "
            "(e.g. local:iso/ubuntu-22.04.iso). Overrides iso_url if set."
        ),
    )
    default_storage = models.CharField(
        max_length=255,
        verbose_name=_("Default storage"),
    )
    default_bridge = models.CharField(
        max_length=64,
        default="vmbr0",
        verbose_name=_("Default bridge"),
    )
    os_family = models.CharField(
        max_length=32,
        choices=PackerOSFamilyChoices,
        verbose_name=_("OS family"),
    )
    os_release = models.CharField(max_length=64, verbose_name=_("OS release"))
    default_ciuser = models.CharField(
        max_length=64,
        default="ubuntu",
        verbose_name=_("Default cloud-init user"),
    )
    provisioner_recipe = models.CharField(
        max_length=32,
        choices=PackerProvisionerRecipeChoices,
        verbose_name=_("Provisioner recipe"),
    )
    default_variables = models.JSONField(
        blank=True,
        default=dict,
        encoder=CustomFieldJSONEncoder,
        verbose_name=_("Default variables"),
    )
    allowed_tenants = models.ManyToManyField(
        to="tenancy.Tenant",
        blank=True,
        related_name="packer_image_definitions",
        verbose_name=_("Allowed tenants"),
        help_text=_("Tenants allowed to use this image definition."),
    )

    class Meta:
        ordering = ("name",)
        verbose_name = _("Packer image definition")
        verbose_name_plural = _("Packer image definitions")
        constraints = [
            models.UniqueConstraint(
                fields=("slug",),
                name="netbox_packer_definition_identity",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.builder_type == PackerBuilderTypeChoices.PROXMOX_CLONE:
            if self.target_cluster_id is None:
                errors["target_cluster"] = str(
                    _(
                        "Target cluster is required for proxmox-clone image "
                        "definitions that publish to the cloud image catalog."
                    )
                )
            if not self.source_template_vmid:
                errors["source_template_vmid"] = str(
                    _("Source template VMID is required for the proxmox-clone builder.")
                )
        elif self.builder_type == PackerBuilderTypeChoices.PROXMOX_ISO:
            if not self.iso_storage and not self.iso_url:
                errors["iso_storage"] = str(
                    _("Either ISO storage reference or ISO URL is required for proxmox-iso builder.")
                )
        if errors:
            raise ValidationError(errors)

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_packer:packerimagedefinition", args=[self.pk])
