"""Application services owned directly by a Proxmox endpoint."""

from __future__ import annotations

from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel

try:
    from ipam.choices import ServiceProtocolChoices

    PROTOCOL_CHOICES = ServiceProtocolChoices
except ImportError:  # pragma: no cover - compatibility with older NetBox layouts
    PROTOCOL_CHOICES = (
        ("tcp", _("TCP")),
        ("udp", _("UDP")),
        ("sctp", _("SCTP")),
    )


class ProxmoxEndpointService(NetBoxModel):
    """A layer-four application service exposed by a Proxmox endpoint."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="application_services",
        verbose_name=_("Proxmox endpoint"),
    )
    name = models.CharField(max_length=100, verbose_name=_("Name"))
    protocol = models.CharField(
        max_length=8,
        choices=PROTOCOL_CHOICES,
        default="tcp",
        verbose_name=_("Protocol"),
    )
    ports = ArrayField(
        base_field=models.PositiveIntegerField(
            validators=[MinValueValidator(1), MaxValueValidator(65535)]
        ),
        verbose_name=_("Ports"),
    )
    ipaddresses = models.ManyToManyField(
        to="ipam.IPAddress",
        related_name="proxbox_application_services",
        blank=True,
        verbose_name=_("IP addresses"),
    )
    description = models.CharField(max_length=200, blank=True)
    comments = models.TextField(blank=True)

    class Meta:
        ordering = ("endpoint", "name")
        verbose_name = _("application service")
        verbose_name_plural = _("application services")
        constraints = (
            models.UniqueConstraint(
                fields=("endpoint", "name"),
                name="netbox_proxbox_endpointservice_unique_endpoint_name",
            ),
        )

    def __str__(self) -> str:
        return f"{self.name} ({self.endpoint})"

    def clean(self) -> None:
        super().clean()
        if not self.ports:
            raise ValidationError({"ports": _("At least one port is required.")})
        self.ports = sorted(set(self.ports))
        if self.pk is None:
            return
        previous_endpoint_id = (
            type(self)
            .objects.filter(pk=self.pk)
            .values_list("endpoint_id", flat=True)
            .first()
        )
        if previous_endpoint_id is None or previous_endpoint_id == self.endpoint_id:
            return
        # The owning endpoint is immutable: moving a service would carry its SSH
        # credential (and any OpenBao assignment) into another endpoint's chain.
        raise ValidationError(
            {
                "endpoint": _(
                    "The owning endpoint of an application service cannot be changed."
                )
            }
        )

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_proxbox:proxmoxendpointservice", args=[self.pk])
