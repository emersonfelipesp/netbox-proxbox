"""Proxmox cluster / API endpoint stored in NetBox for ProxBox sync."""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox_proxbox.choices import (
    ProxmoxAccessMethodChoices,
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
    SSH_CRED_SOURCE_CHOICES,
    SSH_CRED_SOURCE_DEDICATED,
    SSH_CRED_SOURCE_REUSE,
    normalize_fingerprint,
)
from netbox_proxbox.models.primary_secrets import (
    decrypt_primary_secret,
    encrypt_primary_secret,
)
from netbox_proxbox.utils import encryption as enc_helpers


logger = logging.getLogger(__name__)

SERVICE_MONITORING_INELIGIBLE_MESSAGE = _(
    "Service monitoring requires write permission (allow_writes), SSH access "
    "(api_ssh), a registered SSH credential, and netbox-rpc installed and "
    "enabled for this endpoint (effective rpc_enabled). Monitoring dispatches "
    "an RPC execution each tick, which the backend rejects while RPC is "
    "disabled or unavailable."
)


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
    password_enc = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Encrypted password"),
        help_text=_("Fernet-encrypted Proxmox endpoint password ciphertext. Internal."),
    )
    token_name = models.CharField(
        max_length=255,
        verbose_name=_("Token name"),
        blank=True,
    )
    token_value_enc = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Encrypted token value"),
        help_text=_("Fernet-encrypted Proxmox API token value ciphertext. Internal."),
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
    access_methods = models.CharField(
        max_length=16,
        choices=ProxmoxAccessMethodChoices,
        default=ProxmoxAccessMethodChoices.API,
        verbose_name=_("Access methods"),
        help_text=_(
            "Transport access method for this endpoint. 'API only' permits "
            "Read+Write over the Proxmox HTTP API; 'API + SSH' additionally "
            "permits SSH (the browser SSH terminal). SSH only complements API; "
            "there is no SSH-only option. Orthogonal to 'Allow Proxmox-side "
            "writes'. New endpoints default to API only; this value is pushed "
            "to the proxbox-api backend."
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
    sync_mode_vm_interface = models.CharField(
        max_length=16,
        choices=SyncModeChoices,
        null=True,
        blank=True,
        verbose_name=_("VM interface sync mode"),
        help_text=_(
            "Per-endpoint override for VM interface sync. Leave blank to inherit."
        ),
    )
    sync_mode_mac = models.CharField(
        max_length=16,
        choices=SyncModeChoices,
        null=True,
        blank=True,
        verbose_name=_("MAC address sync mode"),
        help_text=_(
            "Per-endpoint override for VM interface MAC sync. Leave blank to inherit."
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
    sync_mode_sdn = models.CharField(
        max_length=16,
        choices=SyncModeChoices,
        null=True,
        blank=True,
        verbose_name=_("SDN sync mode"),
        help_text=_(
            "Per-endpoint override for read-only Proxmox SDN sync. Leave blank to inherit."
        ),
    )
    sync_mode_sdn_bgp = models.CharField(
        max_length=16,
        choices=SyncModeChoices,
        null=True,
        blank=True,
        verbose_name=_("SDN BGP projection sync mode"),
        help_text=_(
            "Per-endpoint override for optional netbox-bgp SDN projection. "
            "Leave blank to inherit."
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
    ssh_credential_source = models.CharField(
        max_length=32,
        choices=SSH_CRED_SOURCE_CHOICES,
        default=SSH_CRED_SOURCE_DEDICATED,
        verbose_name=_("SSH credential source"),
        help_text=_(
            "Choose a dedicated SSH credential or reuse this endpoint's "
            "Proxmox username/password for SSH. Reuse strips the realm "
            "(for example, root@pam becomes root); only PAM-backed Proxmox "
            "users usually map to local SSH accounts."
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
    service_monitoring_enabled = models.BooleanField(
        default=False,
        verbose_name=_("Enable service monitoring"),
        help_text=_(
            "Opt in to agentless systemd service monitoring through netbox-rpc. "
            "Requires Proxmox-side writes enabled, API + SSH access, and complete "
            "endpoint SSH credentials, with netbox-rpc installed and effectively "
            "enabled for this endpoint."
        ),
    )
    service_monitoring_interval_minutes = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(1440)],
        verbose_name=_("Service monitoring interval (minutes)"),
        help_text=_("Polling interval for systemd service monitoring."),
    )
    service_monitoring_units = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Service monitoring units"),
        help_text=_(
            "List of systemd units to collect. Leave empty to let netbox-rpc use "
            "its default Proxmox unit set."
        ),
    )
    service_monitoring_last_success_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Service monitoring last success"),
    )
    service_monitoring_last_status = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name=_("Service monitoring last status"),
    )
    service_monitoring_last_error = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Service monitoring last error"),
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
    rpc_enabled = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("RPC enabled"),
        help_text=_(
            "Per-endpoint override for netbox-rpc operations against this Proxmox "
            "endpoint. Leave blank to inherit the global netbox-rpc setting; set "
            "explicitly to override it when netbox-rpc is installed. If netbox-rpc "
            "is absent, the effective value is always disabled."
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
    enable_tenant_tag_assignment = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        verbose_name=_("Enable tenant tag assignment (override)"),
        help_text=_(
            "Per-endpoint override for the global tenant tag-assignment toggle. "
            "Leave blank to inherit."
        ),
    )
    enable_tenant_from_cluster = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        verbose_name=_("Enable tenant assignment from cluster (override)"),
        help_text=_(
            "Per-endpoint override for the global tenant cluster-inheritance toggle. "
            "Leave blank to inherit."
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
    allowed_tenants = models.ManyToManyField(
        to="tenancy.Tenant",
        blank=True,
        related_name="proxbox_proxmox_endpoints",
        verbose_name=_("Allowed tenants"),
        help_text=_(
            "Tenants explicitly granted access to this endpoint. Leave empty for "
            "default visibility; NMS Cloud callers with any explicit endpoint grant "
            "see only their granted endpoints."
        ),
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
    def password(self) -> str:
        """Decrypt and return the Proxmox password secret."""
        return decrypt_primary_secret(self.password_enc)

    @password.setter
    def password(self, value: object | None) -> None:
        self.password_enc = encrypt_primary_secret(value)

    @property
    def token_value(self) -> str:
        """Decrypt and return the Proxmox API token value secret."""
        return decrypt_primary_secret(self.token_value_enc)

    @token_value.setter
    def token_value(self, value: object | None) -> None:
        self.token_value_enc = encrypt_primary_secret(value)

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
    def effective_ssh_username(self) -> str:
        """Return the SSH login username selected by the endpoint SSH source."""
        if self.ssh_credential_source == SSH_CRED_SOURCE_REUSE:
            return (self.username or "").split("@", 1)[0].strip()
        return (self.ssh_username or "").strip()

    @property
    def ssh_access_enabled(self) -> bool:
        """True when this endpoint permits the SSH transport (``api_ssh``).

        This is the access-method gate (orthogonal to ``allow_writes``). It
        governs whether SSH paths — notably the browser SSH terminal — may be
        used at all, independent of whether SSH credentials are configured.
        """
        return self.access_methods == ProxmoxAccessMethodChoices.API_SSH

    @property
    def has_ssh_terminal_credentials(self) -> bool:
        """Return whether endpoint fallback SSH is complete enough to use."""
        if self.ssh_credential_source == SSH_CRED_SOURCE_REUSE:
            return bool(
                self.ssh_host
                and self.ssh_known_host_fingerprint
                and self.effective_ssh_username
                and self.password
            )
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

    @property
    def service_monitoring_eligible(self) -> bool:
        """Return whether this endpoint can run systemctl service monitoring.

        Service monitoring dispatches an ``RPCExecution`` on every scheduler
        tick, and the nms-backend RPC dispatch gate fails closed on RPC-disabled
        endpoints (403 ``RPC_ENDPOINT_DISABLED``). An endpoint whose effective
        netbox-rpc state is disabled can therefore never succeed, so it is not
        eligible — this keeps ``clean()`` from accepting an enable that would
        403 forever and keeps the scheduler tick / on-demand collect from
        dispatching doomed executions.
        """
        return bool(
            self._service_monitoring_base_eligible() and self.effective_rpc_enabled()
        )

    def _service_monitoring_base_eligible(self) -> bool:
        """Return whether all non-RPC service-monitoring gates are satisfied."""
        return bool(
            self.allow_writes
            and self.ssh_access_enabled
            and self.has_ssh_terminal_credentials
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
        if self.service_monitoring_enabled and not self.service_monitoring_eligible:
            if self._should_auto_disable_service_monitoring_for_rpc():
                self.service_monitoring_enabled = False
                logger.warning(
                    "Auto-disabled service monitoring for Proxmox endpoint %s "
                    "because netbox-rpc is not installed or is disabled for the "
                    "endpoint.",
                    getattr(self, "pk", None) or self,
                )
            else:
                raise ValidationError(
                    {"__all__": SERVICE_MONITORING_INELIGIBLE_MESSAGE}
                )
        if self.ssh_credential_source == SSH_CRED_SOURCE_REUSE:
            errors: dict[str, str] = {}
            if not self.password:
                errors["ssh_credential_source"] = (
                    "Reusing endpoint credentials for SSH requires a stored "
                    "endpoint password; token-only endpoints cannot be reused."
                )
            if not self.ssh_known_host_fingerprint:
                errors["ssh_known_host_fingerprint"] = (
                    "Pinned host-key fingerprint is required when reusing "
                    "endpoint credentials for SSH."
                )
            if errors:
                raise ValidationError(errors)
            return

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

    def effective_rpc_enabled(self) -> bool:
        """Resolve whether netbox-rpc is enabled for this endpoint.

        netbox-rpc installation is a precondition for every path. Once the
        guarded import succeeds, the per-endpoint ``rpc_enabled`` override wins
        when set (an explicit ``False`` is respected via ``is not None``);
        otherwise this inherits the **global** netbox-rpc opt-in flag
        (``RpcPluginSettings.enabled``).

        netbox-rpc is an *optional* companion of netbox-proxbox: it is imported
        function-locally and guarded, so this returns ``False`` when netbox-rpc
        is not installed. This module never imports netbox-rpc at load time and
        must never depend on the NMS stack.
        """
        try:
            from netbox_rpc.models import RpcPluginSettings
        except ImportError:
            return False

        if self.rpc_enabled is not None:
            return bool(self.rpc_enabled)

        try:
            return bool(RpcPluginSettings.get_solo().enabled)
        except Exception:  # noqa: BLE001 - resolution must never break callers
            return False

    def _should_auto_disable_service_monitoring_for_rpc(self) -> bool:
        """Return whether an RPC-only eligibility loss should disable monitoring."""
        return bool(
            self._saved_service_monitoring_enabled()
            and self._service_monitoring_base_eligible()
            and not self.effective_rpc_enabled()
        )

    def _saved_service_monitoring_enabled(self) -> bool:
        """Return the persisted monitoring flag for existing rows, if available."""
        pk = getattr(self, "pk", None)
        if not pk:
            return False
        manager = getattr(type(self), "_default_manager", None) or getattr(
            type(self),
            "objects",
            None,
        )
        if manager is None:
            return False
        try:
            saved = (
                manager.filter(pk=pk)
                .values_list("service_monitoring_enabled", flat=True)
                .first()
            )
        except (AttributeError, TypeError):
            return False
        return bool(saved)

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
        default = (
            SyncModeChoices.DISABLED
            if field_name in {"sync_mode_sdn", "sync_mode_sdn_bgp"}
            else SyncModeChoices.ALWAYS
        )
        return str(getattr(settings, field_name, default) or default)
