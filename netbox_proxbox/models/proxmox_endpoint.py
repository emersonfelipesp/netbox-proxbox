"""Proxmox cluster / API endpoint stored in NetBox for ProxBox sync."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox_proxbox.choices import (
    ProxmoxEndpointEnvironmentChoices,
    ProxmoxModeChoices,
    SyncModeChoices,
)
from netbox_proxbox.constants import OVERWRITE_FIELDS, SYNC_MODE_RESOURCE_TYPES
from netbox_proxbox.fields import DomainField
from netbox_proxbox.models.base import PORT_VALIDATORS, EndpointBase
from netbox_proxbox.models.ssh_credential import (
    AUTH_METHOD_CHOICES,
    AUTH_METHOD_KEY,
    AUTH_METHOD_PASSWORD,
    normalize_fingerprint,
)
from netbox_proxbox.utils import encryption as enc_helpers


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
    sync_mode_vm = models.CharField(
        max_length=16,
        choices=SyncModeChoices,
        null=True,
        blank=True,
        verbose_name=_("VM sync mode"),
        help_text=_(
            "Per-endpoint override for non-template VM synchronization. Leave blank to inherit."
        ),
    )
    sync_mode_vm_template = models.CharField(
        max_length=16,
        choices=SyncModeChoices,
        null=True,
        blank=True,
        verbose_name=_("VM template sync mode"),
        help_text=_(
            "Per-endpoint override for Proxmox template VM synchronization. Leave blank to inherit."
        ),
    )
    sync_mode_cluster = models.CharField(
        max_length=16,
        choices=SyncModeChoices,
        null=True,
        blank=True,
        verbose_name=_("Cluster sync mode"),
        help_text=_(
            "Per-endpoint override for Proxmox cluster tracking sync. Leave blank to inherit."
        ),
    )
    sync_mode_node = models.CharField(
        max_length=16,
        choices=SyncModeChoices,
        null=True,
        blank=True,
        verbose_name=_("Node sync mode"),
        help_text=_(
            "Per-endpoint override for Proxmox node tracking sync. Leave blank to inherit."
        ),
    )
    sync_mode_storage = models.CharField(
        max_length=16,
        choices=SyncModeChoices,
        null=True,
        blank=True,
        verbose_name=_("Storage sync mode"),
        help_text=_(
            "Per-endpoint override for Proxmox storage sync. Leave blank to inherit."
        ),
    )
    sync_mode_ip_address = models.CharField(
        max_length=16,
        choices=SyncModeChoices,
        null=True,
        blank=True,
        verbose_name=_("IP address sync mode"),
        help_text=_(
            "Per-endpoint override for IP address sync. Leave blank to inherit."
        ),
    )
    ssh_username = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name=_("SSH username"),
        help_text=_(
            "Fallback SSH username for the endpoint itself when no per-node "
            "NodeSSHCredential is selected."
        ),
    )
    ssh_port = models.PositiveIntegerField(
        default=22,
        validators=PORT_VALIDATORS,
        verbose_name=_("SSH port"),
        help_text=_("Fallback SSH listener port for this endpoint."),
    )
    ssh_auth_method = models.CharField(
        max_length=8,
        choices=AUTH_METHOD_CHOICES,
        default=AUTH_METHOD_KEY,
        verbose_name=_("SSH authentication method"),
        help_text=_("Prefer key-based authentication. Password is a fallback."),
    )
    ssh_known_host_fingerprint = models.CharField(
        max_length=128,
        blank=True,
        default="",
        verbose_name=_("Pinned SSH host-key SHA-256 fingerprint"),
        help_text=_(
            "Canonical SHA256:<base64> form. Proxbox refuses terminal access "
            "unless the host key matches this exact value."
        ),
    )
    ssh_password_enc = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Encrypted SSH password"),
        help_text=_("Fernet-encrypted fallback SSH password ciphertext. Internal."),
    )
    ssh_private_key_enc = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Encrypted SSH private key"),
        help_text=_("Fernet-encrypted fallback SSH private key ciphertext. Internal."),
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
        ordering = ("name", "pk")
        verbose_name = _("Proxmox endpoint")
        verbose_name_plural = _("Proxmox endpoints")
        permissions = (("open_ssh_terminal", _("Can open Proxbox SSH terminal")),)
        constraints = (
            models.UniqueConstraint(
                fields=("name", "ip_address", "domain"),
                name="netbox_proxbox_proxmoxendpoint_identity",
            ),
        )

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this Proxmox endpoint detail view."""
        return reverse("plugins:netbox_proxbox:proxmoxendpoint", args=[self.pk])

    @property
    def ssh_host(self) -> str:
        """Host string used by the endpoint-level SSH terminal fallback."""
        return (self.domain or self.ip or "").strip()

    @property
    def has_ssh_password(self) -> bool:
        """Return whether an endpoint fallback SSH password ciphertext is stored."""
        return bool(self.ssh_password_enc)

    @property
    def has_ssh_private_key(self) -> bool:
        """Return whether an endpoint fallback SSH private-key ciphertext is stored."""
        return bool(self.ssh_private_key_enc)

    @property
    def has_ssh_terminal_credentials(self) -> bool:
        """Return whether endpoint fallback SSH is complete enough to use."""
        has_secret = (
            self.has_ssh_private_key
            if self.ssh_auth_method == AUTH_METHOD_KEY
            else self.has_ssh_password
        )
        return bool(
            self.ssh_host
            and self.ssh_username
            and self.ssh_known_host_fingerprint
            and has_secret
        )

    def set_ssh_password(self, plaintext: str, *, key: str) -> None:
        """Encrypt and store the endpoint fallback SSH password."""
        self.ssh_password_enc = enc_helpers.encrypt(plaintext, key=key)

    def get_ssh_password(self, *, key: str) -> str:
        """Decrypt and return the endpoint fallback SSH password."""
        return enc_helpers.decrypt(self.ssh_password_enc, key=key)

    def set_ssh_private_key(self, plaintext: str, *, key: str) -> None:
        """Encrypt and store the endpoint fallback SSH private key."""
        self.ssh_private_key_enc = enc_helpers.encrypt(plaintext, key=key)

    def get_ssh_private_key(self, *, key: str) -> str:
        """Decrypt and return the endpoint fallback SSH private key."""
        return enc_helpers.decrypt(self.ssh_private_key_enc, key=key)

    def clean(self) -> None:
        """Validate endpoint identity plus optional SSH terminal fallback fields."""
        super().clean()
        if self.ssh_known_host_fingerprint:
            self.ssh_known_host_fingerprint = normalize_fingerprint(
                self.ssh_known_host_fingerprint
            )
        has_any_ssh = any(
            (
                self.ssh_username,
                self.ssh_known_host_fingerprint,
                self.ssh_password_enc,
                self.ssh_private_key_enc,
            )
        )
        if not has_any_ssh:
            return

        errors: dict[str, str] = {}
        if not self.ssh_username:
            errors["ssh_username"] = "SSH username is required for endpoint fallback."
        if not self.ssh_known_host_fingerprint:
            errors["ssh_known_host_fingerprint"] = (
                "Pinned host-key fingerprint is required for endpoint fallback."
            )
        if self.ssh_auth_method == AUTH_METHOD_KEY and not self.ssh_private_key_enc:
            errors["ssh_auth_method"] = "Key authentication requires a private key."
        if self.ssh_auth_method == AUTH_METHOD_PASSWORD and not self.ssh_password_enc:
            errors["ssh_auth_method"] = "Password authentication requires a password."
        if errors:
            raise ValidationError(errors)

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

    def effective_sync_mode(self, resource_type: str) -> str:
        """Resolve a per-resource sync mode, falling back to the global singleton."""
        from netbox_proxbox.models.plugin_settings import ProxboxPluginSettings

        normalized = str(resource_type or "").strip().lower().replace("-", "_")
        normalized = normalized.removeprefix("sync_mode_")
        if normalized not in SYNC_MODE_RESOURCE_TYPES:
            raise ValueError(f"Unsupported sync mode resource type: {resource_type!r}")

        field_name = f"sync_mode_{normalized}"
        endpoint_value = getattr(self, field_name, None)
        if endpoint_value:
            return str(endpoint_value)
        settings = ProxboxPluginSettings.get_solo()
        return str(getattr(settings, field_name, SyncModeChoices.ALWAYS))
