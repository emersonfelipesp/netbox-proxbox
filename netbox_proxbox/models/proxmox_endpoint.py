"""Proxmox cluster / API endpoint stored in NetBox for ProxBox sync."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox_proxbox.choices import ProxmoxEndpointEnvironmentChoices, ProxmoxModeChoices
from netbox_proxbox.constants import OVERWRITE_FIELDS
from netbox_proxbox.fields import DomainField
from netbox_proxbox.models.base import PORT_VALIDATORS, EndpointBase


class ProxmoxEndpoint(EndpointBase):
    """Credentials and address for a Proxmox VE instance or cluster."""

    name = models.CharField(
        default="Proxmox Endpoint",
        max_length=255,
        blank=True,
        null=True,
        help_text=_(
            "Name of the Proxmox endpoint or cluster. It may be updated from the API."
        ),
    )
    ip_address = models.ForeignKey(
        to="ipam.IPAddress",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("IP address"),
        null=True,
        blank=True,
        help_text=_("Fallback endpoint address when no domain name is configured."),
    )
    domain = DomainField(
        verbose_name=_("Domain"),
        help_text=_("Domain name of the Proxmox endpoint or cluster."),
        blank=True,
        null=True,
    )
    port = models.PositiveIntegerField(
        default=8006,
        validators=PORT_VALIDATORS,
        verbose_name=_("HTTP port"),
    )
    mode = models.CharField(
        max_length=255,
        choices=ProxmoxModeChoices,
        default=ProxmoxModeChoices.PROXMOX_MODE_UNDEFINED,
    )
    environment = models.CharField(
        max_length=32,
        choices=ProxmoxEndpointEnvironmentChoices,
        blank=True,
        null=True,
        verbose_name=_("Environment"),
        help_text=_(
            "Operator-selected lifecycle stage (e.g. production, development, "
            "homologation). Manual classification only; never written by sync."
        ),
    )
    version = models.CharField(max_length=20, blank=True, null=True)
    repoid = models.CharField(
        max_length=16,
        blank=True,
        null=True,
        verbose_name=_("Repository ID"),
    )
    username = models.CharField(
        default="root@pam",
        max_length=255,
        verbose_name=_("Username"),
        help_text=_("Username must use the format 'user@realm'."),
    )
    password = models.CharField(
        max_length=255,
        verbose_name=_("Password"),
        help_text=_(
            "Password for the Proxmox endpoint. Leave blank when using token authentication."
        ),
        blank=True,
        null=True,
    )
    token_name = models.CharField(
        max_length=255,
        verbose_name=_("Token name"),
        blank=True,
    )
    token_value = models.CharField(
        max_length=255,
        verbose_name=_("Token value"),
        blank=True,
    )
    verify_ssl = models.BooleanField(
        default=False,
        verbose_name=_("Verify SSL"),
        help_text=_("Verify the TLS certificate presented by the Proxmox endpoint."),
    )
    allow_writes = models.BooleanField(
        default=False,
        verbose_name=_("Allow Proxmox-side writes"),
        help_text=_(
            "When enabled, operational verbs (start, stop, snapshot, migrate) "
            "may be dispatched against this endpoint. Default off. Enabling "
            "this widens the trust boundary; restrict the new "
            "core.run_proxmox_action permission to a small operator group."
        ),
    )
    timeout = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Timeout (seconds)"),
        help_text=_(
            "Per-endpoint API request timeout in seconds. Leave blank to use the global default."
        ),
    )
    max_retries = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Max retries"),
        help_text=_(
            "Per-endpoint maximum retry attempts for transient failures (GET/HEAD only). "
            "Leave blank to use the global default."
        ),
    )
    retry_backoff = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Retry back-off (seconds)"),
        help_text=_(
            "Per-endpoint exponential back-off base delay in seconds between retries. "
            "Leave blank to use the global default."
        ),
    )
    overwrite_device_role = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite device role"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_device_type = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite device type"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_device_tags = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite device tags"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_device_status = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite device status"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_device_description = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite device description"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_device_custom_fields = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite device custom fields"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_vm_role = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite VM role"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_vm_type = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite VM type"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_vm_tags = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Merge VM tags"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_vm_proxmox_tags = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Sync Proxmox tags"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_vm_description = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite VM description"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_vm_custom_fields = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite VM custom fields"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_vm_cloudinit = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite VM cloud-init"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_cluster_tags = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite cluster tags"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_cluster_description = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite cluster description"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_cluster_custom_fields = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite cluster custom fields"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_node_interface_tags = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite node interface tags"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_node_interface_custom_fields = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite node interface custom fields"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_storage_tags = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite storage tags"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_vm_interface_tags = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite VM interface tags"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_vm_interface_custom_fields = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite VM interface custom fields"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_ip_status = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite IP status"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_ip_tags = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite IP tags"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_ip_custom_fields = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite IP custom fields"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    overwrite_ip_address_dns_name = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Overwrite IP address DNS name"),
        help_text=_(
            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
        ),
    )
    default_role_qemu = models.ForeignKey(
        to="dcim.DeviceRole",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
        limit_choices_to={"vm_role": True},
        verbose_name=_("Default QEMU VM role"),
        help_text=_(
            "Per-endpoint override for the global default QEMU VM role. Leave blank to inherit."
        ),
    )
    default_role_lxc = models.ForeignKey(
        to="dcim.DeviceRole",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
        limit_choices_to={"vm_role": True},
        verbose_name=_("Default LXC container role"),
        help_text=_(
            "Per-endpoint override for the global default LXC container role. Leave blank to inherit."
        ),
    )
    enable_tenant_name_regex = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Enable tenant regex (override)"),
        help_text=_(
            "Per-endpoint override for the global tenant-regex toggle. Leave blank to inherit."
        ),
    )
    tenant_name_regex_rules = models.JSONField(
        null=True,
        blank=True,
        default=None,
        verbose_name=_("Tenant regex rules (override)"),
        help_text=_(
            "Per-endpoint override for the global rule list. Leave null to inherit. "
            "When set (even to an empty list), replaces the global list for this endpoint."
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
        verbose_name = _("Proxmox endpoint")
        verbose_name_plural = _("Proxmox endpoints")
        constraints = (
            models.UniqueConstraint(
                fields=("name", "ip_address", "domain"),
                name="netbox_proxbox_proxmoxendpoint_identity",
            ),
        )

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this Proxmox endpoint detail view."""
        return reverse("plugins:netbox_proxbox:proxmoxendpoint", args=[self.pk])

    def effective_overwrites(self) -> dict[str, bool]:
        """Resolve overwrite flags by falling back to the global plugin singleton when NULL."""
        from netbox_proxbox.models.plugin_settings import ProxboxPluginSettings

        settings = ProxboxPluginSettings.get_solo()
        return {
            name: getattr(self, name)
            if getattr(self, name) is not None
            else getattr(settings, name)
            for name in OVERWRITE_FIELDS
        }
