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
        verbose_name=_("Source template VMID"),
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
        if (
            self.builder_type == PackerBuilderTypeChoices.PROXMOX_CLONE
            and self.target_cluster_id is None
        ):
            raise ValidationError(
                {
                    "target_cluster": _(
                        "Target cluster is required for proxmox-clone image "
                        "definitions that publish to the cloud image catalog."
                    )
                }
            )

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_packer:packerimagedefinition", args=[self.pk])
