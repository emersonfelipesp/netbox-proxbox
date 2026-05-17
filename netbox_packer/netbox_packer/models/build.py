"""Packer image build execution model."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel
from utilities.json import CustomFieldJSONEncoder

from netbox_packer.choices import PackerBuildStatusChoices


class PackerImageBuild(NetBoxModel):
    """One Packer image build execution requested from NetBox."""

    definition = models.ForeignKey(
        to="netbox_packer.PackerImageDefinition",
        on_delete=models.PROTECT,
        related_name="builds",
        verbose_name=_("Image definition"),
    )
    status = models.CharField(
        max_length=32,
        choices=PackerBuildStatusChoices,
        default=PackerBuildStatusChoices.PENDING,
        verbose_name=_("Status"),
    )
    backend_build_id = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Backend build ID"),
    )
    proxmox_endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.PROTECT,
        related_name="packer_image_builds",
        verbose_name=_("Proxmox endpoint"),
    )
    target_node = models.CharField(max_length=255, verbose_name=_("Target node"))
    output_vmid = models.PositiveIntegerField(verbose_name=_("Output VMID"))
    output_name = models.CharField(max_length=255, verbose_name=_("Output name"))
    image_version = models.CharField(max_length=64, verbose_name=_("Image version"))
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Started at"),
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Completed at"),
    )
    created_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="packer_image_builds",
        verbose_name=_("Created by"),
    )
    netbox_job_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("NetBox job ID"),
    )
    cloud_image_template = models.ForeignKey(
        to="netbox_proxbox.CloudImageTemplate",
        on_delete=models.SET_NULL,
        related_name="packer_image_builds",
        null=True,
        blank=True,
        verbose_name=_("Cloud image template"),
    )
    backend_response = models.JSONField(
        blank=True,
        default=dict,
        encoder=CustomFieldJSONEncoder,
        verbose_name=_("Backend response"),
    )
    error = models.TextField(blank=True, verbose_name=_("Error"))

    class Meta:
        ordering = ("-started_at", "-created")
        verbose_name = _("Packer image build")
        verbose_name_plural = _("Packer image builds")
        indexes = [
            models.Index(
                fields=("status", "started_at"),
                name="netbox_packer_build_status_started",
            )
        ]

    def __str__(self) -> str:
        return f"{self.definition} {self.image_version}"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_packer:packerimagebuild", args=[self.pk])
