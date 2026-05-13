"""Reflected PBS node/host record."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel


class PBSNode(NetBoxModel):
    """Per-PBS-host status reflected from ``GET /nodes/{node}/status``."""

    endpoint = models.ForeignKey(
        to="netbox_pbs.PBSEndpoint",
        on_delete=models.CASCADE,
        related_name="nodes",
    )
    hostname = models.CharField(
        max_length=255,
        help_text=_("PBS node hostname as returned by the PBS API."),
    )
    version = models.CharField(
        max_length=64,
        blank=True,
        help_text=_("PBS server software version (e.g. ``3.2.7``)."),
    )
    uptime_seconds = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Uptime (seconds)"),
    )
    cpu_pct = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("CPU usage (%)"),
    )
    memory_used = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Memory used (bytes)"),
    )
    memory_total = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Memory total (bytes)"),
    )
    last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Last seen at"),
    )

    class Meta:
        ordering = ("endpoint", "hostname")
        verbose_name = _("PBS node")
        verbose_name_plural = _("PBS nodes")
        constraints = (
            models.UniqueConstraint(
                fields=("endpoint", "hostname"),
                name="netbox_pbs_pbsnode_identity",
            ),
        )

    def __str__(self) -> str:
        return f"{self.endpoint} / {self.hostname}"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_pbs:pbsnode", args=[self.pk])
