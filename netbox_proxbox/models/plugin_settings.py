"""Persistent plugin-level settings for ProxBox behavior toggles."""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel

DEFAULT_BACKEND_LOG_FILE_PATH = "/var/log/proxbox.log"

PRIMARY_IP_PREFERENCE_CHOICES = (
    ("ipv4", _("Prefer IPv4")),
    ("ipv6", _("Prefer IPv6")),
)

BRANCH_ON_CONFLICT_CHOICES = (
    ("fail", _("Fail (leave branch open for review)")),
    ("acknowledge", _("Acknowledge and merge anyway")),
)

RECONCILIATION_ENGINE_CHOICES = (
    ("python", _("Python (default)")),
    ("compare", _("Compare Python and Rust")),
    ("rust", _("Rust + PyO3")),
)

NETBOX_TO_PROXMOX_TYPED_PHRASE = "allow-edit-and-add-actions"


def parse_cidr_list(text: str) -> list[str]:
    """Parse newline-separated CIDR ranges into a list of strings."""
    if not text:
        return []
    return [line.strip() for line in text.split("\n") if line.strip()]


class ProxboxPluginSettings(NetBoxModel):
    """Singleton-style settings row used by plugin UI and sync jobs."""

    singleton_key = models.CharField(
        max_length=32,
        unique=True,
        default="default",
        editable=False,
    )
    use_guest_agent_interface_name = models.BooleanField(
        default=True,
        verbose_name=_("Use guest agent interface name"),
        help_text=_(
            "When enabled, VM interface names use QEMU guest-agent names when available "
            "(for example ens18) instead of generic Proxmox labels (for example net0/nic0)."
        ),
    )
    proxbox_fetch_max_concurrency = models.PositiveSmallIntegerField(
        default=8,
        verbose_name=_("Proxmox fetch max concurrency"),
        help_text=_(
            "Maximum number of parallel Proxmox fetch operations per sync stage. "
            "Higher values can speed up multi-cluster discovery but may increase load."
        ),
    )
    ignore_ipv6_link_local_addresses = models.BooleanField(
        default=True,
        verbose_name=_("Ignore IPv6 link-local addresses"),
        help_text=_(
            "When enabled, IPv6 link-local addresses (fe80::/64) are ignored during "
            "VM interface IP address selection. Disable this only if you need link-local "
            "addresses to be included."
        ),
    )
    ensure_netbox_objects = models.BooleanField(
        default=True,
        verbose_name=_("Ensure NetBox supporting objects on startup"),
        help_text=_(
            "When enabled, proxbox-api runs an idempotent NetBox-side bootstrap pass "
            "on each process startup that ensures the supporting objects the plugin "
            "requires (cluster type, device roles, manufacturer, device type, VM type, "
            "custom fields, discovery tags) exist. Disable to leave hand-curated "
            "NetBox installs untouched."
        ),
    )
    delete_orphans = models.BooleanField(
        default=False,
        verbose_name=_("Delete orphan VMs"),
        help_text=_(
            "When enabled, full-update runs will delete Proxbox-discovered VMs "
            "that were not touched by the current sync run. Review a dry-run "
            "preview before enabling in production."
        ),
    )
    primary_ip_preference = models.CharField(
        max_length=4,
        choices=PRIMARY_IP_PREFERENCE_CHOICES,
        default="ipv4",
        verbose_name=_("Primary IP preference"),
        help_text=_(
            "Preferred IP family when Proxbox selects the VM primary IP. "
            "Choose IPv4 or IPv6."
        ),
    )
    netbox_max_concurrent = models.PositiveSmallIntegerField(
        default=1,
        verbose_name=_("NetBox max concurrent requests"),
        help_text=_(
            "Maximum number of simultaneous in-flight requests to the NetBox API (semaphore cap). "
            "Increase carefully — PostgreSQL pool may exhaust."
        ),
    )
    netbox_timeout = models.PositiveIntegerField(
        default=120,
        verbose_name=_("NetBox client timeout (seconds)"),
        help_text=_(
            "Timeout for proxbox-api → NetBox HTTP requests. "
            "Increase when NetBox runs slow large queries."
        ),
    )
    netbox_write_concurrency = models.PositiveSmallIntegerField(
        default=8,
        verbose_name=_("NetBox write concurrency"),
        help_text=_(
            "Maximum concurrent NetBox write operations (creates/updates) used by VM, "
            "snapshot, and task-history sync paths."
        ),
    )
    proxmox_fetch_concurrency = models.PositiveSmallIntegerField(
        default=8,
        verbose_name=_("Proxmox fetch concurrency"),
        help_text=_(
            "Maximum concurrent Proxmox read operations used by backup, snapshot, "
            "and task-history discovery."
        ),
    )
    netbox_max_retries = models.PositiveSmallIntegerField(
        default=5,
        verbose_name=_("NetBox max retries"),
        help_text=_("Maximum retry attempts for transient NetBox API failures."),
    )
    netbox_retry_delay = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("2.00"),
        verbose_name=_("NetBox retry delay (seconds)"),
        help_text=_("Base delay in seconds for exponential back-off between retries."),
    )
    netbox_get_cache_ttl = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=Decimal("60.00"),
        verbose_name=_("NetBox GET cache TTL (seconds)"),
        help_text=_(
            "How long to cache NetBox GET responses in memory. Set to 0 to disable caching."
        ),
    )
    netbox_get_cache_max_entries = models.PositiveIntegerField(
        default=4096,
        verbose_name=_("NetBox GET cache max entries"),
        help_text=_(
            "Maximum number of entries kept in the in-memory NetBox GET cache before "
            "least-recently-used entries are evicted."
        ),
    )
    netbox_get_cache_max_bytes = models.PositiveBigIntegerField(
        default=52_428_800,
        verbose_name=_("NetBox GET cache max bytes"),
        help_text=_(
            "Maximum total size in bytes of the in-memory NetBox GET cache. "
            "Default is 50 MiB."
        ),
    )
    bulk_batch_size = models.PositiveSmallIntegerField(
        default=50,
        verbose_name=_("Bulk batch size"),
        help_text=_("Number of records per batch in bulk create/update operations."),
    )
    bulk_batch_delay_ms = models.PositiveIntegerField(
        default=500,
        verbose_name=_("Bulk batch delay (ms)"),
        help_text=_(
            "Milliseconds to wait between bulk batches to avoid overwhelming NetBox."
        ),
    )
    backup_batch_size = models.PositiveSmallIntegerField(
        default=5,
        verbose_name=_("Backup batch size"),
        help_text=_(
            "Number of VM backup records processed per batch during backup sync."
        ),
    )
    backup_batch_delay_ms = models.PositiveIntegerField(
        default=200,
        verbose_name=_("Backup batch delay (ms)"),
        help_text=_(
            "Milliseconds to wait between backup batches to throttle Proxmox/NetBox load."
        ),
    )
    vm_sync_max_concurrency = models.PositiveSmallIntegerField(
        default=4,
        verbose_name=_("VM sync max concurrency"),
        help_text=_("Maximum number of VMs synced in parallel during a full update."),
    )
    reconciliation_engine = models.CharField(
        max_length=16,
        choices=RECONCILIATION_ENGINE_CHOICES,
        default="python",
        verbose_name=_("VM reconciliation engine"),
        help_text=_(
            "Engine used by proxbox-api to build VM operation queues. Python is the "
            "default implementation; compare runs Python and Rust then returns Python "
            "output; rust requires the optional proxbox-reconcile-rs PyO3 package."
        ),
    )
    reconciliation_compare_strict = models.BooleanField(
        default=False,
        verbose_name=_("Strict Rust comparison"),
        help_text=_(
            "When VM reconciliation engine is compare, raise an error if Rust output "
            "differs from Python output. Use for validation, not normal production sync."
        ),
    )
    custom_fields_request_delay = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Custom fields request delay (seconds)"),
        help_text=_(
            "Optional sleep between custom-field API operations to throttle requests."
        ),
    )
    backend_log_file_path = models.CharField(
        max_length=255,
        default=DEFAULT_BACKEND_LOG_FILE_PATH,
        verbose_name=_("Backend log file path"),
        help_text=_(
            "Absolute file path for proxbox-api rotated log archive output "
            "(for example /var/log/proxbox.log). Changes apply after proxbox-api restart."
        ),
    )
    debug_cache = models.BooleanField(
        default=False,
        verbose_name=_("Debug cache logging"),
        help_text=_(
            "When enabled, proxbox-api emits verbose log entries for NetBox GET cache "
            "hits, misses, and evictions. Useful for diagnosing cache behavior."
        ),
    )
    expose_internal_errors = models.BooleanField(
        default=False,
        verbose_name=_("Expose internal errors"),
        help_text=_(
            "When enabled, proxbox-api includes internal exception details in HTTP error "
            "responses. Leave disabled in production to avoid leaking implementation details."
        ),
    )
    parse_description_metadata = models.BooleanField(
        default=False,
        verbose_name=_("Parse description metadata"),
        help_text=_(
            "When enabled, proxbox-api reads each Proxmox object's description for a "
            "fenced ``netbox-metadata`` JSON block and applies the parsed PK ids to the "
            "matching NetBox fields. Per-field ``overwrite_*`` flags still gate keys "
            "they cover. Disabled by default."
        ),
    )
    embed_description_metadata = models.BooleanField(
        default=False,
        verbose_name=_("Embed description metadata"),
        help_text=_(
            "When enabled, intent-direction create/update writes to Proxmox append a "
            "fenced ``netbox-metadata`` JSON block of NetBox FK ids (role, tenant, "
            "site, platform, cluster, device) to the Proxmox object's description. "
            "Pairs with ``parse_description_metadata`` to round-trip NetBox metadata "
            "through Proxmox without drift. Disabled by default."
        ),
    )
    ssrf_protection_enabled = models.BooleanField(
        default=True,
        verbose_name=_("Enable SSRF protection"),
        help_text=_(
            "When enabled, validates that Proxmox/NetBox/FastAPI endpoints do not point to "
            "reserved or internal IP addresses. Disable only in trusted environments."
        ),
    )
    allow_private_ips = models.BooleanField(
        default=True,
        verbose_name=_("Allow private IP addresses"),
        help_text=_(
            "When enabled, allows endpoints with private IP addresses (10.0.0.0/8, "
            "172.16.0.0/12, 192.168.0.0/16). Recommended for on-premises deployments."
        ),
    )
    additional_allowed_ip_ranges = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Additional allowed IP CIDR ranges"),
        help_text=_(
            "One CIDR range per line (e.g., 10.30.0.0/16). IPs in these ranges are always allowed, "
            "regardless of other SSRF settings."
        ),
    )
    explicitly_blocked_ip_ranges = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Explicitly blocked IP CIDR ranges"),
        help_text=_(
            "One CIDR range per line. IPs in these ranges are always blocked, "
            "even if they match allowed ranges above."
        ),
    )
    encryption_key = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Encryption key"),
        help_text=_(
            "Base64-encoded or raw encryption key for proxbox-api credential encryption. "
            "If set, proxbox-api will use this key instead of PROXBOX_ENCRYPTION_KEY env var. "
            "Leave blank to use environment variable only."
        ),
    )
    proxmox_timeout = models.PositiveIntegerField(
        default=5,
        verbose_name=_("Proxmox API timeout (seconds)"),
        help_text=_(
            "Default timeout in seconds for Proxmox API requests. "
            "Individual endpoints can override this value."
        ),
    )
    proxmox_max_retries = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("Proxmox max retries"),
        help_text=_(
            "Default maximum retry attempts for transient Proxmox API failures (GET/HEAD only). "
            "Individual endpoints can override this value."
        ),
    )
    proxmox_retry_backoff = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.50"),
        verbose_name=_("Proxmox retry back-off (seconds)"),
        help_text=_(
            "Default exponential back-off base delay in seconds between Proxmox retries. "
            "Individual endpoints can override this value."
        ),
    )
    overwrite_device_role = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite device role"),
        help_text=_(
            "When disabled, sync never changes the device role on existing Proxmox node devices "
            "that already have a role assigned. The role is still set when the device is first created."
        ),
    )
    overwrite_device_type = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite device type"),
        help_text=_(
            "When disabled, sync never changes the device type on existing Proxmox node devices "
            "that already have a device type assigned. The device type is still set at create time."
        ),
    )
    overwrite_device_tags = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite device tags"),
        help_text=_(
            "When disabled, sync never changes the tags on existing Proxmox node devices "
            "that already have tags assigned. Tags are still applied when the device is first created."
        ),
    )
    overwrite_vm_role = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite VM role"),
        help_text=_(
            "When disabled, sync never changes the role on existing NetBox virtual machines "
            "that already have a role assigned. The role is still set when the VM is first created."
        ),
    )
    overwrite_vm_type = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite VM type"),
        help_text=_(
            "When disabled, sync never changes the type on existing NetBox virtual machines "
            "that already have a type assigned. The type is still set when the VM is first created."
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
            "Default DeviceRole assigned to QEMU virtual machines synced from Proxmox. "
            "Per-Endpoint and per-Node values override this; operator edits on a specific "
            "VirtualMachine are preserved by the last-synced-role snapshot lock."
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
            "Default DeviceRole assigned to LXC containers synced from Proxmox. "
            "Per-Endpoint and per-Node values override this; operator edits on a specific "
            "VirtualMachine are preserved by the last-synced-role snapshot lock."
        ),
    )
    overwrite_vm_tags = models.BooleanField(
        default=True,
        verbose_name=_("Merge VM tags"),
        help_text=_(
            "When enabled, sync merges existing NetBox VM tags with the Proxbox tag, preserving "
            "user-assigned tags. When disabled, sync never changes tags on existing virtual "
            "machines; tags are still applied at VM creation."
        ),
    )
    overwrite_vm_proxmox_tags = models.BooleanField(
        default=True,
        verbose_name=_("Sync Proxmox tags"),
        help_text=_(
            "When enabled, Proxmox VM tags (the `;`-separated `tags` field on QEMU/LXC config) "
            "are mirrored as NetBox tags on the synced VirtualMachine. Tag colors match the "
            "Proxmox `tag-style` color-map when available, otherwise a stable deterministic "
            "color is used. When disabled, Proxmox-sourced tags are never created or attached."
        ),
    )
    overwrite_device_status = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite device status"),
        help_text=_(
            "When disabled, sync never changes the status on existing Proxmox node devices."
        ),
    )
    overwrite_device_description = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite device description"),
        help_text=_(
            "When disabled, sync never changes the description on existing Proxmox node devices."
        ),
    )
    overwrite_device_custom_fields = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite device custom fields"),
        help_text=_(
            "When disabled, sync never changes custom fields on existing Proxmox node devices."
        ),
    )
    overwrite_vm_description = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite VM description"),
        help_text=_(
            "When disabled, sync never changes the description on existing NetBox virtual machines."
        ),
    )
    overwrite_vm_custom_fields = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite VM custom fields"),
        help_text=_(
            "When disabled, sync never changes custom fields on existing NetBox virtual machines."
        ),
    )
    overwrite_vm_cloudinit = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite VM cloud-init"),
        help_text=_(
            "When disabled, sync never updates the ProxmoxVMCloudInit row "
            "(ciuser, sshkeys, ipconfig0) on existing NetBox virtual machines."
        ),
    )
    overwrite_cluster_tags = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite cluster tags"),
        help_text=_(
            "When disabled, sync never changes tags on existing NetBox virtualization clusters."
        ),
    )
    overwrite_cluster_description = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite cluster description"),
        help_text=_(
            "When disabled, sync never changes the description on existing NetBox virtualization clusters."
        ),
    )
    overwrite_cluster_custom_fields = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite cluster custom fields"),
        help_text=_(
            "When disabled, sync never changes custom fields on existing NetBox virtualization clusters."
        ),
    )
    overwrite_node_interface_tags = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite node interface tags"),
        help_text=_(
            "When disabled, sync never changes tags on existing physical interfaces of Proxmox node devices."
        ),
    )
    overwrite_node_interface_custom_fields = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite node interface custom fields"),
        help_text=_(
            "When disabled, sync never changes custom fields on existing physical interfaces of Proxmox node devices."
        ),
    )
    overwrite_storage_tags = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite storage tags"),
        help_text=_(
            "When disabled, sync never changes tags on existing ProxmoxStorage records."
        ),
    )
    overwrite_vm_interface_tags = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite VM interface tags"),
        help_text=_(
            "When disabled, sync never changes tags on existing virtual-machine interfaces."
        ),
    )
    overwrite_vm_interface_custom_fields = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite VM interface custom fields"),
        help_text=_(
            "When disabled, sync never changes custom fields on existing virtual-machine interfaces."
        ),
    )
    overwrite_ip_status = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite IP status"),
        help_text=_(
            "When disabled, sync never changes the status of existing IP addresses assigned to VM interfaces."
        ),
    )
    overwrite_ip_tags = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite IP tags"),
        help_text=_(
            "When disabled, sync never changes tags on existing IP addresses assigned to VM interfaces."
        ),
    )
    overwrite_ip_custom_fields = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite IP custom fields"),
        help_text=_(
            "When disabled, sync never changes custom fields on existing IP addresses assigned to VM interfaces."
        ),
    )
    overwrite_ip_address_dns_name = models.BooleanField(
        default=True,
        verbose_name=_("Overwrite IP address DNS name"),
        help_text=_(
            "When disabled, sync never changes the dns_name field on existing IP addresses; dns_name is still populated when an IP is created."
        ),
    )
    enable_tenant_name_regex = models.BooleanField(
        default=False,
        verbose_name=_("Enable tenant assignment by VM-name regex"),
        help_text=_(
            "When enabled, sync resolves a NetBox Tenant for VMs by matching the "
            "VM name against the rules below. Disabled by default. Existing "
            "tenant assignments are never overwritten."
        ),
    )
    tenant_name_regex_rules = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Tenant name regex rules"),
        help_text=_(
            "Ordered list of {pattern, tenant_slug, [label]} dicts. First match "
            "wins; specificity-first ordering is recommended (e.g. '^cust-acme-' "
            "before '^cust-'). Patterns are compiled and tenant slugs are verified "
            "at save time."
        ),
    )
    branching_enabled = models.BooleanField(
        default=False,
        verbose_name=_("Branching-enabled sync (Proxmox → NetBox)"),
        help_text=_(
            "When enabled, every Proxbox sync job creates a fresh netbox-branching "
            "branch, runs the sync on that branch, and merges it back into main on "
            "success. Requires the netbox_branching plugin to be installed and listed "
            "last in PLUGINS."
        ),
    )
    branch_name_prefix = models.CharField(
        max_length=64,
        default="proxbox-sync",
        verbose_name=_("Branch name prefix"),
        help_text=_(
            "Prefix used when auto-creating a NetBox branch per sync job "
            "(e.g. proxbox-sync-<job_id>-<timestamp>)."
        ),
    )
    branch_on_conflict = models.CharField(
        max_length=16,
        choices=BRANCH_ON_CONFLICT_CHOICES,
        default="fail",
        verbose_name=_("Branch merge conflict policy"),
        help_text=_(
            "What to do when the auto-created sync branch reports merge conflicts. "
            "'fail' leaves the branch open for operator review and marks the job failed. "
            "'acknowledge' attempts the merge anyway and delegates conflict handling "
            "to the netbox-branching merge strategy."
        ),
    )
    netbox_to_proxmox_enabled = models.BooleanField(
        default=False,
        verbose_name=_("Enable NetBox → Proxmox intent direction"),
        help_text=_(
            "Master flag for the intent-direction integration: merging a branch flagged "
            "apply_to_proxmox=True dispatches CREATE/UPDATE writes to Proxmox via "
            "proxbox-api. DELETE still requires the separate DeletionRequest authorization "
            "chain. Off by default."
        ),
    )
    netbox_to_proxmox_typed_confirmation = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name=_("Typed confirmation phrase"),
        help_text=_(
            "Operators enabling NetBox → Proxmox writes must type the exact phrase "
            "'allow-edit-and-add-actions' into this field. Toggling the master flag back "
            "to off clears this phrase, forcing a re-confirmation on re-enable."
        ),
    )
    intent_warn_plaintext_password = models.BooleanField(
        default=True,
        verbose_name=_("Warn on plaintext cloud-init passwords"),
        help_text=_(
            "When enabled, the intent merge validator emits a warning if "
            "cloud_init_user_data contains a plaintext password line."
        ),
    )
    apply_destroy_confirmed = models.BooleanField(
        default=False,
        verbose_name=_("Allow apply-destroy authorization workflow"),
        help_text=_(
            "Per-branch destroy master switch. Even when set, every destroy still flows "
            "through a separate DeletionRequest approved by a user holding "
            "netbox_proxbox.authorize_deletion_request. Off by default."
        ),
    )
    intent_apply_authorization_self_approve_allowed = models.BooleanField(
        default=False,
        verbose_name=_("Allow deletion request self-approval"),
        help_text=_(
            "When enabled, the user who requested a Proxmox deletion may also approve "
            "the DeletionRequest. Leave disabled for four-eyes authorization."
        ),
    )
    intent_deletion_request_ttl_days = models.IntegerField(
        default=7,
        validators=[MinValueValidator(1)],
        verbose_name=_("Deletion request TTL (days)"),
        help_text=_(
            "Pending DeletionRequests older than this many days are auto-rejected "
            "and the pending-deletion tag is removed from Proxmox best-effort."
        ),
    )
    hardware_discovery_enabled = models.BooleanField(
        default=False,
        verbose_name=_("Enable SSH-based hardware discovery"),
        help_text=_(
            "Master flag for the SSH-driven hardware-discovery pass. When enabled, "
            "proxbox-api opens a pinned-fingerprint SSH session to each ProxmoxNode that "
            "has a stored NodeSSHCredential row, runs dmidecode + ethtool + ip link under "
            "sudo -n, and reflects the parsed chassis / NIC values onto the matching "
            "dcim.Device and dcim.Interface custom fields. Off by default — flipping off "
            "results in zero SSH sockets opened during sync."
        ),
    )

    class Meta:
        verbose_name = _("Proxbox plugin settings")
        verbose_name_plural = _("Proxbox plugin settings")

    def __str__(self) -> str:
        return "Proxbox plugin settings"

    def save(self, *args: object, **kwargs: object) -> None:
        """Handle save."""
        self.singleton_key = "default"
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        """Return absolute url."""
        return reverse("plugins:netbox_proxbox:settings")

    @classmethod
    def get_solo(cls) -> "ProxboxPluginSettings":
        """Return solo."""
        obj, _ = cls.objects.get_or_create(singleton_key="default")
        return obj

    def get_allowed_ip_ranges(self) -> list[str]:
        """Return list of additional allowed CIDR ranges."""
        return parse_cidr_list(self.additional_allowed_ip_ranges)

    def get_blocked_ip_ranges(self) -> list[str]:
        """Return list of explicitly blocked CIDR ranges."""
        return parse_cidr_list(self.explicitly_blocked_ip_ranges)
