"""Reflected PBS datastore."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel

from netbox_pbs.choices import PBSDatastoreGCStatusChoices


class PBSDatastore(NetBoxModel):
    """Per-PBS datastore reflected from ``GET /admin/datastore``."""

    endpoint = models.ForeignKey(
        to="netbox_pbs.PBSEndpoint",
        on_delete=models.CASCADE,
        related_name="datastores",
    )
    name = models.CharField(
        max_length=255,
        help_text=_("PBS datastore name."),
    )
    path = models.CharField(
        max_length=512,
        blank=True,
        help_text=_("On-disk path of the datastore on the PBS host."),
    )
    total_bytes = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Total (bytes)"),
    )
    used_bytes = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Used (bytes)"),
    )
    available_bytes = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Available (bytes)"),
    )
    gc_status = models.CharField(
        max_length=16,
        choices=PBSDatastoreGCStatusChoices,
        default=PBSDatastoreGCStatusChoices.GC_STATUS_UNKNOWN,
    )
    last_gc_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Last GC at"),
    )

    class Meta:
        ordering = ("endpoint", "name")
        verbose_name = _("PBS datastore")
        verbose_name_plural = _("PBS datastores")
        constraints = (
            models.UniqueConstraint(
                fields=("endpoint", "name"),
                name="netbox_pbs_pbsdatastore_identity",
            ),
        )

    def __str__(self) -> str:
        return f"{self.endpoint} / {self.name}"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_pbs:pbsdatastore", args=[self.pk])
