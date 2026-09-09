"""Plugin-owned Proxmox InfluxDB metrics configuration."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel

CREDENTIAL_FREE_HTTP_URL_RE = r"^[Hh][Tt][Tt][Pp][Ss]://[^/?#@\s]+(?:/[^?#\s]*)?$"
MASKED_SECRET = "********"
MASKED_INFLUX_URL = MASKED_SECRET
_INFLUX_URL_VALIDATOR = URLValidator(schemes=("https",))


def masked_influx_url(value: str | None) -> str:
    """Return only a valid credential-free HTTPS InfluxDB base URL."""
    if (
        not isinstance(value, str)
        or not value
        or not re.fullmatch(CREDENTIAL_FREE_HTTP_URL_RE, value)
    ):
        return MASKED_INFLUX_URL
    try:
        _INFLUX_URL_VALIDATOR(value)
        parsed_url = urlsplit(value)
    except (ValidationError, ValueError):
        return MASKED_INFLUX_URL
    if "@" in parsed_url.netloc or parsed_url.query or parsed_url.fragment:
        return MASKED_INFLUX_URL
    return value


class ProxmoxMetricsInfluxDB(NetBoxModel):
    """InfluxDB query endpoint metadata for a Proxmox cluster.

    Tokens are encrypted with the plugin's Fernet key. Ciphertext fields are
    internal and never appear in API or audit representations; callers use
    write-only inputs and the server decrypts only for the backend query proxy.
    """

    name = models.CharField(max_length=100, default="default", verbose_name=_("Name"))
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
            "Credential-free InfluxDB base URL, for example https://influxdb.example:8086."
        ),
    )
    org = models.CharField(
        max_length=128, default="nmulticloud", verbose_name=_("InfluxDB organization")
    )
    bucket = models.CharField(
        max_length=128, default="proxmox", verbose_name=_("InfluxDB bucket")
    )
    measurement_prefix = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Measurement prefix"),
        help_text=_(
            "Optional Flux measurement prefix used by the Proxmox metrics writer."
        ),
    )
    query_token_enc = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Encrypted query token"),
        help_text=_("Fernet-encrypted InfluxDB query token. Internal."),
    )
    verify_tls = models.BooleanField(default=True, verbose_name=_("Verify TLS"))
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
            ),
            models.CheckConstraint(
                condition=models.Q(query_token_enc__gt="") | models.Q(enabled=False),
                name="netbox_proxbox_metrics_influxdb_query_token_configured",
            ),
            models.CheckConstraint(
                condition=models.Q(enabled=False)
                | models.Q(influx_url__regex=CREDENTIAL_FREE_HTTP_URL_RE),
                name="netbox_proxbox_metrics_influxdb_url_is_safe",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} -> {self.proxmox_cluster}"

    @property
    def has_query_token(self) -> bool:
        """Return whether an encrypted query token is stored."""
        from netbox_proxbox.services.encryption_recovery import ciphertext_state

        return ciphertext_state(self.query_token_enc) == "configured"

    @property
    def credential_encryption_state(self) -> str:
        """Return a secret-free state for list and edit recovery UX."""
        from netbox_proxbox.services.encryption_recovery import ciphertext_state

        states = (ciphertext_state(self.query_token_enc),)
        if "recovery_required" in states:
            return "Recovery required"
        if "configured" in states:
            return "Configured"
        return "Not configured"

    def set_query_token(self, plaintext: str, *, key: str) -> None:
        """Encrypt and store the query token with the supplied Fernet key."""
        from netbox_proxbox.utils import encryption as enc_helpers
        from netbox_proxbox.services.encryption_recovery import (
            mark_encrypted_fields_for_write,
        )

        mark_encrypted_fields_for_write(self, "query_token_enc")
        self.query_token_enc = enc_helpers.encrypt(plaintext, key=key)

    def get_query_token(self, *, key: str) -> str:
        """Decrypt and return the stored query token."""
        from netbox_proxbox.utils import encryption as enc_helpers

        return enc_helpers.decrypt(self.query_token_enc, key=key)

    def serialize_object(self, exclude=None):
        """Mask URL and ciphertext in NetBox change-log snapshots."""
        data = super().serialize_object(exclude=exclude)
        if "influx_url" in data:
            data["influx_url"] = masked_influx_url(data["influx_url"])
        if "query_token_enc" in data:
            data["query_token_enc"] = MASKED_SECRET if data["query_token_enc"] else ""
        return data

    @property
    def influx_url_display(self) -> str:
        """Fail-closed rendering value for :attr:`influx_url`."""
        return masked_influx_url(self.influx_url)

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
            if (
                not re.fullmatch(CREDENTIAL_FREE_HTTP_URL_RE, self.influx_url)
                or parsed_url is None
                or "@" in parsed_url.netloc
                or parsed_url.query
                or parsed_url.fragment
            ):
                raise ValidationError(
                    {
                        "influx_url": _(
                            "Use the InfluxDB base URL without userinfo, query, or fragment."
                        )
                    }
                )
        from netbox_proxbox.services.encryption_recovery import ciphertext_state

        if self.enabled and ciphertext_state(self.query_token_enc) != "configured":
            raise ValidationError(
                {
                    "query_token_enc": _(
                        "An encrypted query token is required when metrics are enabled."
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
