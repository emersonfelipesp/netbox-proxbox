"""Abstract endpoint base and shared URL-related mixins for ProxBox models."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel

from utilities.views import get_viewname

from netbox_proxbox.fields import DomainField

PORT_VALIDATORS = (MinValueValidator(1), MaxValueValidator(65535))


class CommonProperties:
    """IP and HTTP(S) URL helpers for endpoint models."""

    @property
    def ip(self) -> str | None:
        """Dotted IPv4/IPv6 host string from the linked ``IPAddress``, if any."""
        return str(self.ip_address.address.ip) if self.ip_address else None

    @property
    def url(self) -> str:
        """Synthetic ``http(s)://`` base URL using domain or IP and the model port."""
        protocol = "https" if self.verify_ssl else "http"
        host = self.domain or self.ip
        return f"{protocol}://{host}:{self.port}" if host else ""


class EndpointBase(CommonProperties, NetBoxModel):
    """Shared identity fields for HTTP-reachable plugin endpoints."""

    name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )
    ip_address = models.ForeignKey(
        to="ipam.IPAddress",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("IP address"),
        null=True,
        blank=True,
    )
    domain = DomainField(
        verbose_name=_("Domain"),
        blank=True,
        null=True,
    )
    port = models.PositiveIntegerField(
        validators=PORT_VALIDATORS,
        verbose_name=_("HTTP port"),
    )
    verify_ssl = models.BooleanField(
        verbose_name=_("Verify SSL"),
    )

    class Meta:
        abstract = True
        ordering = ("name", "pk")

    @classmethod
    def _get_action_url(cls, action, rest_api, kwargs):
        """
        Endpoint REST list URLs live under the nested ``endpoints`` include
        (``plugins-api:netbox_proxbox-api:endpoints:{model}-list``), not the flat
        name NetBox's get_viewname() builds. APISelect / DynamicModel* fields call
        get_action_url(..., action=\"list\", rest_api=True).
        """
        if rest_api and action == "list":
            mn = cls._meta.model_name
            return reverse(f"plugins-api:netbox_proxbox-api:endpoints:{mn}-list")
        return reverse(get_viewname(cls, action, rest_api), kwargs=kwargs or {})

    def __str__(self) -> str:
        """Prefer name, then domain, then IP. Requires at least one identifier."""
        return (
            self.name
            or self.domain
            or self.ip
            or f"{self.__class__.__name__}({self.pk})"
        )

    def clean(self) -> None:
        """Ensure at least one resolvable host (domain or IP object) is configured."""
        super().clean()
        if not (self.domain or self.ip_address_id):
            raise ValidationError(
                {
                    "domain": "Provide either a domain or an IP address.",
                    "ip_address": "Provide either a domain or an IP address.",
                }
            )
