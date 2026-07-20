"""Proxmox metrics integration metadata."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel


NMS_SECRET_REF_RE = (
    r"^nms-secret:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class ProxmoxMetricsInfluxDB(NetBoxModel):
    """InfluxDB query endpoint metadata for a Proxmox cluster."""

    name = models.CharField(
        max_length=100,
        default="default",
        verbose_name=_("Name"),
        help_text=_("Operator label for this InfluxDB metrics endpoint."),
    )
    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="metrics_influxdb_endpoints",
        verbose_name=_("Proxmox endpoint"),
        help_text=_("Proxmox endpoint whose cluster writes to this InfluxDB server."),
    )
    proxmox_cluster = models.ForeignKey(
        to="netbox_proxbox.ProxmoxCluster",
        on_delete=models.CASCADE,
        related_name="metrics_influxdb_endpoints",
        verbose_name=_("Proxmox cluster"),
        help_text=_("Proxmox cluster associated with this InfluxDB bucket."),
    )
    influx_url = models.URLField(
        max_length=255,
        verbose_name=_("InfluxDB URL"),
        help_text=_(
            "Base URL for InfluxDB, for example https://influxdb.example:8086."
        ),
    )
    org = models.CharField(
        max_length=128,
        default="nmulticloud",
        verbose_name=_("InfluxDB organization"),
    )
    bucket = models.CharField(
        max_length=128,
        default="proxmox",
        verbose_name=_("InfluxDB bucket"),
    )
    measurement_prefix = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Measurement prefix"),
        help_text=_(
            "Optional Flux measurement prefix used by the Proxmox metrics writer."
        ),
    )
    query_token_secret_ref = models.CharField(
        max_length=80,
        validators=[RegexValidator(regex=NMS_SECRET_REF_RE)],
        verbose_name=_("Query token secret reference"),
        help_text=_("netbox-nms ObservabilitySecret reference, not plaintext."),
    )
    writer_token_secret_ref = models.CharField(
        max_length=80,
        blank=True,
        validators=[RegexValidator(regex=NMS_SECRET_REF_RE)],
        verbose_name=_("Writer token secret reference"),
        help_text=_("Optional PVE writer token reference for configuring Proxmox."),
    )
    verify_tls = models.BooleanField(
        default=True,
        verbose_name=_("Verify TLS"),
        help_text=_("Verify the InfluxDB server certificate when querying metrics."),
    )
    enabled = models.BooleanField(
        default=True,
        verbose_name=_("Enabled"),
        help_text=_("Disabled mappings are inventory-only and must not be queried."),
    )
    comments = models.TextField(blank=True)

    class Meta:
        ordering = ("endpoint", "proxmox_cluster", "name")
        verbose_name = _("Proxmox InfluxDB metrics endpoint")
        verbose_name_plural = _("Proxmox InfluxDB metrics endpoints")
        constraints = [
            models.UniqueConstraint(
                fields=["proxmox_cluster", "name"],
                name="netbox_proxbox_metrics_influxdb_unique_cluster_name",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} -> {self.proxmox_cluster}"

    def get_absolute_url(self) -> str:
        try:
            return reverse(
                "plugins:netbox_proxbox:proxmoxmetricsinfluxdb", args=[self.pk]
            )
        except NoReverseMatch:
            return ""

    def clean(self) -> None:
        super().clean()
        if self.influx_url:
            try:
                parsed_url = urlsplit(self.influx_url)
            except ValueError:
                parsed_url = None
            if parsed_url and (
                "@" in parsed_url.netloc or parsed_url.query or parsed_url.fragment
            ):
                raise ValidationError(
                    {
                        "influx_url": _(
                            "Use the InfluxDB base URL without userinfo, query, or fragment."
                        )
                    }
                )

        if self.proxmox_cluster_id and self.endpoint_id:
            cluster_endpoint_id = getattr(self.proxmox_cluster, "endpoint_id", None)
            if cluster_endpoint_id and cluster_endpoint_id != self.endpoint_id:
                raise ValidationError(
                    {
                        "proxmox_cluster": _(
                            "The selected Proxmox cluster must belong to the selected endpoint."
                        )
                    }
                )

        for field_name in ("query_token_secret_ref", "writer_token_secret_ref"):
            value = getattr(self, field_name, "") or ""
            if value and not re.fullmatch(NMS_SECRET_REF_RE, value):
                raise ValidationError(
                    {field_name: _("Use a netbox-nms nms-secret:<uuid> reference.")}
                )
