"""Proxmox Datacenter Manager (PDM) endpoint stored in NetBox for ProxBox sync.

PDM is the upstream "manager of managers" service that aggregates one or more
PVE clusters and PBS instances behind a single API and dashboard. In ProxBox
terms a `PDMEndpoint` row is both:

- A third remote service type alongside `ProxmoxEndpoint` (PVE) and
  `PBSEndpoint` — credentials authorize PDM API calls on port 8443.
- An **umbrella record** linking the operator-declared set of PVE clusters
  and PBS instances this PDM federates, via the `proxmox_endpoints` and
  `pbs_endpoints` M2M fields. These declared links are the authoritative
  truth; `PDMRemote.linked_*` rows reflect the discovered truth and any
  drift is surfaced to the operator.
"""

from __future__ import annotations

from django.db import models
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

from netbox_proxbox.models.base import PORT_VALIDATORS, EndpointBase


class PDMEndpoint(EndpointBase):
    """Credentials, address, and federation mapping for a PDM instance."""

    name = models.CharField(
        default="PDM Endpoint",
        max_length=255,
        blank=True,
        null=True,
        help_text=_("Name of the PDM endpoint. May be updated from the PDM API."),
    )
    port = models.PositiveIntegerField(
        default=8443,
        validators=PORT_VALIDATORS,
        verbose_name=_("HTTP port"),
    )
    token_id = models.CharField(
        max_length=255,
        verbose_name=_("Token ID"),
        help_text=_("PDM API token id of the form 'user@realm!tokenname'."),
    )
    token_secret = models.CharField(
        max_length=255,
        verbose_name=_("Token secret"),
        help_text=_("PDM API token secret value."),
    )
    fingerprint = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("TLS fingerprint"),
        help_text=_("PDM server TLS fingerprint pinned at connection time. Optional."),
    )
    verify_ssl = models.BooleanField(
        default=True,
        verbose_name=_("Verify SSL"),
        help_text=_("Verify the TLS certificate presented by the PDM endpoint."),
    )
    allow_writes = models.BooleanField(
        default=False,
        verbose_name=_("Allow PDM-side writes"),
        help_text=_(
            "Reserved for a future PDM-side write surface (remote add/remove, "
            "guest migrate/remote-migrate). Default off; v1 integration is read-only."
        ),
    )
    timeout = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Timeout (seconds)"),
        help_text=_(
            "Per-endpoint API request timeout in seconds. Leave blank for the global default."
        ),
    )
    proxmox_endpoints = models.ManyToManyField(
        to="netbox_proxbox.ProxmoxEndpoint",
        related_name="pdm_endpoints",
        blank=True,
        verbose_name=_("Federated PVE endpoints"),
        help_text=_(
            "Operator-declared set of PVE endpoints this PDM federates. "
            "Compared against discovered `PDMRemote.linked_proxmox_endpoint` "
            "rows after sync; mismatches surface as a drift warning."
        ),
    )
    pbs_endpoints = models.ManyToManyField(
        to="netbox_proxbox.PBSEndpoint",
        related_name="pdm_endpoints",
        blank=True,
        verbose_name=_("Federated PBS endpoints"),
        help_text=_(
            "Operator-declared set of PBS endpoints this PDM federates. "
            "Compared against discovered `PDMRemote.linked_pbs_endpoint` "
            "rows after sync; mismatches surface as a drift warning."
        ),
    )
    site = models.ForeignKey(
        to="dcim.Site",
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("Site"),
        null=True,
        blank=True,
    )
    tenant = models.ForeignKey(
        to="tenancy.Tenant",
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("Tenant"),
        null=True,
        blank=True,
    )

    class Meta(EndpointBase.Meta):
        verbose_name = _("PDM endpoint")
        verbose_name_plural = _("PDM endpoints")
        constraints = (
            models.UniqueConstraint(
                fields=("name", "ip_address", "domain"),
                name="netbox_proxbox_pdmendpoint_identity",
            ),
        )

    @property
    def host(self) -> str:
        """Plain hostname string expected by proxbox-api's PDMEndpoint SQLite model.

        proxbox-api stores endpoints with a single ``host`` field; the Django model
        uses ``domain`` and ``ip_address`` from ``EndpointBase``. This property
        provides a compatible value so sync code can use the same field name.
        """
        return self.domain or self.ip or ""

    @property
    def timeout_seconds(self) -> int:
        """Timeout in seconds matching proxbox-api's ``PDMEndpoint.timeout_seconds`` field.

        proxbox-api names the field ``timeout_seconds``; Django uses ``timeout``.
        This property bridges the name difference so sync code can reference either
        model interchangeably.
        """
        return self.timeout if self.timeout is not None else 30

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this PDM endpoint detail view.

        URL routes land in Phase 2 of #449; until then, degrade gracefully
        rather than raise ``NoReverseMatch`` if a changelog or template
        helper tries to linkify the row.
        """
        try:
            return reverse("plugins:netbox_proxbox:pdmendpoint", args=[self.pk])
        except NoReverseMatch:
            return ""
