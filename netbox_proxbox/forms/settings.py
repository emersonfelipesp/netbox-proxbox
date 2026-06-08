"""Forms for plugin-level ProxBox settings."""

import json
import re
from pathlib import PurePosixPath

from django import forms

from dcim.models import DeviceRole
from utilities.forms.fields import DynamicModelChoiceField

from netbox_proxbox.choices import SyncModeChoices
from netbox_proxbox.constants import OVERWRITE_FIELDS, SYNC_MODE_FIELDS
from netbox_proxbox.models.plugin_settings import (
    BRANCH_ON_CONFLICT_CHOICES,
    DEFAULT_BACKEND_LOG_FILE_PATH,
    NETBOX_TO_PROXMOX_TYPED_PHRASE,
    RECONCILIATION_ENGINE_CHOICES,
)


def _sync_mode_choice_options(
    *, include_inherit: bool = False
) -> tuple[tuple[str, str], ...]:
    choices = tuple(
        (value, str(label)) for value, label, _color in SyncModeChoices.CHOICES
    )
    if include_inherit:
        return (("", "Inherit global setting"), *choices)
    return choices


def _parse_tenant_regex_rules(
    raw: object,
    *,
    allow_none: bool,
) -> list[dict] | None:
    """Validate and normalize tenant regex rules.

    When ``allow_none`` is True, empty/whitespace input returns ``None``
    (the per-endpoint "inherit" sentinel). Otherwise empty input returns
    ``[]`` (the global "no rules configured" state).

    Each rule must be an object with non-empty string ``pattern`` and
    ``tenant_slug``. ``pattern`` must compile as a regex. ``tenant_slug``
    must reference an existing ``tenancy.Tenant``. ``label`` is optional.
    Duplicate patterns are rejected.
    """
    if isinstance(raw, list):
        rules = raw
    else:
        text = (raw or "").strip() if isinstance(raw, str) else ""
        if not text:
            return None if allow_none else []
        try:
            rules = json.loads(text)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"Invalid JSON: {exc}") from exc

    if not isinstance(rules, list):
        raise forms.ValidationError("Expected a JSON list of rule objects.")
    if allow_none and rules == []:
        # Explicit "override with empty" stays as [], distinct from None.
        return []

    from tenancy.models import Tenant

    errors: list[str] = []
    cleaned: list[dict] = []
    seen: set[str] = set()
    for i, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            errors.append(f"Rule #{i}: must be an object.")
            continue
        pattern = rule.get("pattern")
        slug = rule.get("tenant_slug")
        if not isinstance(pattern, str) or not pattern:
            errors.append(f"Rule #{i}: 'pattern' must be a non-empty string.")
            continue
        if not isinstance(slug, str) or not slug:
            errors.append(f"Rule #{i}: 'tenant_slug' must be a non-empty string.")
            continue
        try:
            re.compile(pattern)
        except re.error as exc:
            errors.append(f"Rule #{i}: invalid regex {pattern!r} — {exc}.")
            continue
        rule_ok = True
        if not Tenant.objects.filter(slug=slug).exists():
            errors.append(f"Rule #{i}: tenant slug '{slug}' does not exist.")
            rule_ok = False
        if pattern in seen:
            errors.append(f"Rule #{i}: duplicate pattern '{pattern}'.")
            rule_ok = False
        seen.add(pattern)
        if rule_ok:
            entry: dict = {"pattern": pattern, "tenant_slug": slug}
            label = rule.get("label")
            if isinstance(label, str) and label:
                entry["label"] = label
            cleaned.append(entry)
    if errors:
        raise forms.ValidationError(errors)
    return cleaned


class ProxboxPluginSettingsForm(forms.Form):
    """Toggle behavior flags that affect proxbox-api sync requests."""

    use_guest_agent_interface_name = forms.BooleanField(
        required=False,
        label="Use QEMU guest-agent interface names",
        help_text=(
            "When enabled, synced VM interface names prefer guest-agent names "
            "when they are available."
        ),
    )
    proxbox_fetch_max_concurrency = forms.IntegerField(
        required=True,
        min_value=1,
        max_value=64,
        initial=8,
        label="Proxmox fetch max concurrency",
        help_text=(
            "Maximum number of parallel Proxmox fetch operations per sync stage. "
            "Use lower values to reduce backend/API pressure."
        ),
    )
    ignore_ipv6_link_local_addresses = forms.BooleanField(
        required=False,
        label="Ignore IPv6 link-local addresses",
        help_text=(
            "When enabled, IPv6 link-local addresses (fe80::/64) are ignored during "
            "VM interface IP address selection. Disable only if you need link-local addresses included."
        ),
    )
    ensure_netbox_objects = forms.BooleanField(
        required=False,
        label="Ensure NetBox supporting objects on startup",
        help_text=(
            "When enabled, proxbox-api runs an idempotent NetBox-side bootstrap pass "
            "on each process startup that ensures the supporting objects the plugin "
            "requires (cluster type, device roles, manufacturer, device type, VM type, "
            "custom fields, discovery tags) exist. Disable to leave hand-curated "
            "NetBox installs untouched."
        ),
    )
    delete_orphans = forms.BooleanField(
        required=False,
        label="Delete orphan VMs",
        help_text=(
            "When enabled, full-update runs will delete Proxbox-discovered VMs "
            "that were not touched by the current sync run. Review the full-update "
            "dry-run preview before enabling in production."
        ),
    )
    primary_ip_preference = forms.ChoiceField(
        required=True,
        choices=(("ipv4", "Prefer IPv4"), ("ipv6", "Prefer IPv6")),
        initial="ipv4",
        label="Primary IP preference",
        help_text="Preferred IP family when Proxbox selects the VM primary IP.",
    )
    netbox_max_concurrent = forms.IntegerField(
        required=True,
        min_value=1,
        max_value=32,
        initial=1,
        label="NetBox max concurrent requests",
        help_text="Maximum simultaneous in-flight requests to NetBox API. Increase carefully.",
    )
    netbox_timeout = forms.IntegerField(
        required=True,
        min_value=1,
        max_value=3600,
        initial=120,
        label="NetBox client timeout (seconds)",
        help_text="Timeout for proxbox-api → NetBox HTTP requests.",
    )
    netbox_write_concurrency = forms.IntegerField(
        required=True,
        min_value=1,
        max_value=64,
        initial=8,
        label="NetBox write concurrency",
        help_text="Maximum concurrent NetBox write operations (creates/updates).",
    )
    proxmox_fetch_concurrency = forms.IntegerField(
        required=True,
        min_value=1,
        max_value=64,
        initial=8,
        label="Proxmox fetch concurrency",
        help_text="Maximum concurrent Proxmox read operations during sync.",
    )
    netbox_max_retries = forms.IntegerField(
        required=True,
        min_value=1,
        max_value=20,
        initial=5,
        label="NetBox max retries",
        help_text="Maximum retry attempts for transient NetBox API failures.",
    )
    netbox_retry_delay = forms.DecimalField(
        required=True,
        min_value=0,
        max_value=60,
        initial="2.00",
        label="NetBox retry delay (seconds)",
        help_text="Base delay in seconds for exponential back-off between retries.",
    )
    netbox_get_cache_ttl = forms.DecimalField(
        required=True,
        min_value=0,
        max_value=3600,
        initial="60.00",
        label="NetBox GET cache TTL (seconds)",
        help_text="How long to cache NetBox GET responses. Set to 0 to disable caching.",
    )
    netbox_get_cache_max_entries = forms.IntegerField(
        required=True,
        min_value=1,
        max_value=1_000_000,
        initial=4096,
        label="NetBox GET cache max entries",
        help_text="Max number of NetBox GET cache entries before LRU eviction.",
    )
    netbox_get_cache_max_bytes = forms.IntegerField(
        required=True,
        min_value=1,
        max_value=10_737_418_240,
        initial=52_428_800,
        label="NetBox GET cache max bytes",
        help_text="Max total bytes of the NetBox GET cache (default 50 MiB).",
    )
    bulk_batch_size = forms.IntegerField(
        required=True,
        min_value=1,
        max_value=1000,
        initial=50,
        label="Bulk batch size",
        help_text="Number of records per batch in bulk create/update operations.",
    )
    bulk_batch_delay_ms = forms.IntegerField(
        required=True,
        min_value=0,
        max_value=10000,
        initial=500,
        label="Bulk batch delay (ms)",
        help_text="Milliseconds to wait between bulk batches to avoid overwhelming NetBox.",
    )
    backup_batch_size = forms.IntegerField(
        required=True,
        min_value=1,
        max_value=1000,
        initial=5,
        label="Backup batch size",
        help_text="Number of VM backup records processed per batch during backup sync.",
    )
    backup_batch_delay_ms = forms.IntegerField(
        required=True,
        min_value=0,
        max_value=10000,
        initial=200,
        label="Backup batch delay (ms)",
        help_text="Milliseconds to wait between backup batches.",
    )
    vm_sync_max_concurrency = forms.IntegerField(
        required=True,
        min_value=1,
        max_value=64,
        initial=4,
        label="VM sync max concurrency",
        help_text="Maximum number of VMs synced in parallel during a full update.",
    )
    interface_batch_size = forms.IntegerField(
        required=True,
        min_value=1,
        max_value=1000,
        initial=5,
        label="Interface batch size",
        help_text=(
            "Number of VM interfaces (and their IPs, subnets, VLANs) synced per batch. "
            "Large VMs (50+ interfaces) may timeout if synced all at once; batching "
            "prevents overwhelming NetBox with concurrent API calls."
        ),
    )
    interface_batch_delay_ms = forms.IntegerField(
        required=True,
        min_value=0,
        max_value=10000,
        initial=100,
        label="Interface batch delay (ms)",
        help_text="Milliseconds to wait between interface batches to throttle NetBox load.",
    )
    reconciliation_engine = forms.ChoiceField(
        required=True,
        choices=RECONCILIATION_ENGINE_CHOICES,
        initial="python",
        label="VM reconciliation engine",
        help_text=(
            "Choose how proxbox-api builds VM operation queues. Python is the safe "
            "default; compare validates Rust parity while returning Python output; "
            "rust requires proxbox-reconcile-rs or a PyO3-enabled backend image."
        ),
    )
    reconciliation_compare_strict = forms.BooleanField(
        required=False,
        label="Strict Rust comparison",
        help_text=(
            "Only applies to compare mode. When enabled, a Rust/Python mismatch fails "
            "the sync instead of only logging the mismatch."
        ),
    )
    custom_fields_request_delay = forms.DecimalField(
        required=False,
        min_value=0,
        max_value=60,
        initial="0.00",
        label="Custom fields request delay (seconds)",
        help_text="Optional sleep between custom-field API operations to throttle requests.",
    )
    backend_log_file_path = forms.CharField(
        required=True,
        max_length=255,
        initial=DEFAULT_BACKEND_LOG_FILE_PATH,
        label="Backend log file path",
        help_text=(
            "Absolute file path for proxbox-api rotated log archive output "
            "(for example /var/log/proxbox.log). Takes effect after proxbox-api restart."
        ),
    )
    debug_cache = forms.BooleanField(
        required=False,
        label="Debug cache logging",
        help_text=(
            "When enabled, proxbox-api emits verbose log entries for NetBox GET cache "
            "hits, misses, and evictions."
        ),
    )
    expose_internal_errors = forms.BooleanField(
        required=False,
        label="Expose internal errors",
        help_text=(
            "When enabled, proxbox-api includes internal exception details in HTTP error "
            "responses. Leave disabled in production."
        ),
    )
    parse_description_metadata = forms.BooleanField(
        required=False,
        label="Parse description metadata",
        help_text=(
            "When enabled, proxbox-api reads each Proxmox object's description for a "
            'fenced "netbox-metadata" JSON block and applies the parsed PK ids to the '
            "matching NetBox fields. Per-field overwrite_* flags still gate keys they "
            "cover. Disabled by default."
        ),
    )
    embed_description_metadata = forms.BooleanField(
        required=False,
        label="Embed description metadata",
        help_text=(
            "When enabled, intent-direction create/update writes to Proxmox append a "
            'fenced "netbox-metadata" JSON block of NetBox FK ids (role, tenant, site, '
            "platform, cluster, device) to the Proxmox object's description. Pairs "
            "with parse_description_metadata to round-trip NetBox metadata through "
            "Proxmox without drift. Disabled by default."
        ),
    )
    ssrf_protection_enabled = forms.BooleanField(
        required=False,
        label="Enable SSRF protection",
        help_text=(
            "When enabled, validates that endpoints do not point to reserved or internal IP addresses. "
            "Disable only in trusted environments."
        ),
    )
    allow_private_ips = forms.BooleanField(
        required=False,
        label="Allow private IP addresses",
        help_text=(
            "When enabled, allows endpoints with private IP addresses (10.0.0.0/8, "
            "172.16.0.0/12, 192.168.0.0/16). Recommended for on-premises deployments."
        ),
    )
    additional_allowed_ip_ranges = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "cols": 40}),
        label="Additional allowed IP CIDR ranges",
        help_text=(
            "One CIDR range per line (e.g., 10.30.0.0/16). IPs in these ranges are always allowed, "
            "regardless of other SSRF settings."
        ),
    )
    explicitly_blocked_ip_ranges = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "cols": 40}),
        label="Explicitly blocked IP CIDR ranges",
        help_text=(
            "One CIDR range per line. IPs in these ranges are always blocked, "
            "even if they match allowed ranges above."
        ),
    )
    encryption_enabled = forms.BooleanField(
        required=False,
        label="Enable credential encryption",
        help_text=(
            "When enabled, proxbox-api will use the encryption key below to encrypt "
            "credentials at rest. Disabling this clears the stored key."
        ),
    )
    encryption_key = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.PasswordInput(render_value=False),
        label="Encryption key",
        help_text=(
            "Base64-encoded or raw encryption key for proxbox-api credential encryption. "
            "If set, proxbox-api will use this key instead of PROXBOX_ENCRYPTION_KEY environment variable. "
            "Leave blank to use environment variable only."
        ),
    )
    proxmox_timeout = forms.IntegerField(
        required=True,
        min_value=1,
        max_value=300,
        initial=5,
        label="Proxmox API timeout (seconds)",
        help_text="Default timeout in seconds for Proxmox API requests. Individual endpoints can override this.",
    )
    proxmox_max_retries = forms.IntegerField(
        required=True,
        min_value=0,
        max_value=20,
        initial=0,
        label="Proxmox max retries",
        help_text="Default max retry attempts for transient Proxmox API failures (GET/HEAD only). Individual endpoints can override this.",
    )
    proxmox_retry_backoff = forms.DecimalField(
        required=True,
        min_value=0,
        max_value=30,
        initial="0.50",
        label="Proxmox retry back-off (seconds)",
        help_text="Default exponential back-off base delay in seconds between Proxmox retries. Individual endpoints can override this.",
    )
    default_role_qemu = DynamicModelChoiceField(
        queryset=DeviceRole.objects.all(),
        required=False,
        query_params={"vm_role": "true"},
        label="Default QEMU VM role",
        help_text=(
            "Plugin-global default role applied to newly synced QEMU virtual machines. "
            "Per-endpoint and per-node overrides take precedence."
        ),
    )
    default_role_lxc = DynamicModelChoiceField(
        queryset=DeviceRole.objects.all(),
        required=False,
        query_params={"vm_role": "true"},
        label="Default LXC container role",
        help_text=(
            "Plugin-global default role applied to newly synced LXC containers. "
            "Per-endpoint and per-node overrides take precedence."
        ),
    )
    enable_tenant_name_regex = forms.BooleanField(
        required=False,
        label="Enable tenant assignment by VM-name regex",
        help_text=(
            "When enabled, sync resolves a NetBox Tenant for VMs by matching the VM "
            "name against the rules below. Disabled by default. Existing tenant "
            "assignments are never overwritten."
        ),
    )
    tenant_name_regex_rules = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 6, "cols": 60}),
        label="Tenant name regex rules (JSON)",
        help_text=(
            "JSON list of {pattern, tenant_slug, [label]} objects. First match wins; "
            "order more specific patterns first. Patterns are compiled and tenant "
            "slugs are verified on save."
        ),
    )
    enable_tenant_tag_assignment = forms.BooleanField(
        required=False,
        label="Enable tenant assignment by tags",
        help_text=(
            "When enabled, sync assigns a tenant to VMs carrying both the "
            "cloud-customer marker tag and exactly one tenant-<slug> tag. Existing "
            "tenant assignments are never overwritten."
        ),
    )
    branching_enabled = forms.BooleanField(
        required=False,
        label="Branching-enabled sync (Proxmox → NetBox)",
        help_text=(
            "When enabled, every Proxbox sync job creates a fresh netbox-branching "
            "branch, runs the sync on that branch, and merges it back into main on "
            "success. Requires netbox_branching to be installed and listed last in "
            "PLUGINS."
        ),
    )
    branch_name_prefix = forms.CharField(
        required=True,
        max_length=64,
        initial="proxbox-sync",
        label="Branch name prefix",
        help_text=(
            "Prefix used when auto-creating a NetBox branch per sync job "
            "(e.g. proxbox-sync-<job_id>-<timestamp>)."
        ),
    )
    branch_on_conflict = forms.ChoiceField(
        required=True,
        choices=BRANCH_ON_CONFLICT_CHOICES,
        initial="fail",
        label="Branch merge conflict policy",
        help_text=(
            "Policy when the auto-created sync branch reports merge conflicts. "
            "'fail' leaves the branch open and marks the job failed. 'acknowledge' "
            "retries the merge with acknowledge_conflicts=True."
        ),
    )
    netbox_to_proxmox_enabled = forms.BooleanField(
        required=False,
        label="Enable NetBox → Proxmox intent direction",
        help_text=(
            "Master flag for intent-direction writes. Off by default. Enabling this "
            "widens the trust boundary — see the warning in the docs."
        ),
    )
    hardware_discovery_enabled = forms.BooleanField(
        required=False,
        label="Enable SSH-based hardware discovery",
        help_text=(
            "Master flag for the SSH hardware-discovery pass. Off by default. When "
            "enabled, proxbox-api opens an SSH session to each ProxmoxNode that has a "
            "stored NodeSSHCredential row and reflects dmidecode/ethtool output onto "
            "the matching dcim.Device and dcim.Interface custom fields."
        ),
    )
    netbox_to_proxmox_typed_confirmation = forms.CharField(
        required=False,
        max_length=64,
        label="Typed confirmation phrase",
        help_text=(
            "Operators enabling NetBox → Proxmox writes must type the exact phrase "
            f"'{NETBOX_TO_PROXMOX_TYPED_PHRASE}' here. Cleared automatically when the "
            "master flag is turned off."
        ),
    )
    intent_warn_plaintext_password = forms.BooleanField(
        required=False,
        initial=True,
        label="Warn on plaintext cloud-init passwords",
        help_text=(
            "When enabled, branch merge validation warns if cloud_init_user_data "
            "contains a plaintext password line."
        ),
    )
    apply_destroy_confirmed = forms.BooleanField(
        required=False,
        label="Allow apply-destroy authorization workflow",
        help_text=(
            "Per-branch destroy master switch. Destroys still flow through a separate "
            "DeletionRequest approved by a user holding "
            "netbox_proxbox.authorize_deletion_request."
        ),
    )
    intent_apply_authorization_self_approve_allowed = forms.BooleanField(
        required=False,
        label="Allow deletion request self-approval",
        help_text=(
            "When enabled, the user who requested a Proxmox deletion may also approve "
            "the DeletionRequest. Leave disabled for four-eyes authorization."
        ),
    )
    intent_deletion_request_ttl_days = forms.IntegerField(
        required=True,
        min_value=1,
        initial=7,
        label="Deletion request TTL (days)",
        help_text=(
            "Pending DeletionRequests older than this many days are auto-rejected "
            "and the pending-deletion tag is removed from Proxmox best-effort."
        ),
    )

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        sync_mode_labels = {
            "sync_mode_vm": "VM sync mode",
            "sync_mode_vm_template": "VM template sync mode",
            "sync_mode_vm_interface": "VM interface sync mode",
            "sync_mode_mac": "MAC address sync mode",
            "sync_mode_cluster": "Cluster sync mode",
            "sync_mode_node": "Node sync mode",
            "sync_mode_storage": "Storage sync mode",
            "sync_mode_ip_address": "IP address sync mode",
        }
        sync_mode_help = {
            "sync_mode_vm": "Controls non-template VM sync.",
            "sync_mode_vm_template": "Controls Proxmox template VM sync.",
            "sync_mode_vm_interface": "Controls VM interface sync.",
            "sync_mode_mac": "Controls VM interface MAC address reconciliation.",
            "sync_mode_cluster": "Controls Proxmox cluster tracking sync.",
            "sync_mode_node": "Controls Proxmox node tracking sync.",
            "sync_mode_storage": "Controls Proxmox storage sync.",
            "sync_mode_ip_address": "Controls IP address sync from VM interfaces.",
        }
        for name in SYNC_MODE_FIELDS:
            self.fields[name] = forms.ChoiceField(
                required=True,
                choices=_sync_mode_choice_options(),
                initial=SyncModeChoices.ALWAYS,
                label=sync_mode_labels[name],
                help_text=sync_mode_help[name],
            )
        for name in OVERWRITE_FIELDS:
            label = name.removeprefix("overwrite_").replace("_", " ").capitalize()
            if name == "overwrite_vm_tags":
                label = "Merge VM tags"
            elif name == "overwrite_vm_proxmox_tags":
                label = "Sync Proxmox tags"
            self.fields[name] = forms.BooleanField(
                required=False,
                initial=True,
                label=label,
                help_text=(
                    "When disabled, sync never changes this field on existing records. "
                    "It is still set when the object is first created."
                ),
            )

    def clean_tenant_name_regex_rules(self) -> list[dict]:
        """Normalize tenant regex rules JSON; empty input means no rules."""
        return (
            _parse_tenant_regex_rules(
                self.cleaned_data.get("tenant_name_regex_rules"),
                allow_none=False,
            )
            or []
        )

    def clean_backend_log_file_path(self) -> str:
        """Require an absolute log file path including a filename."""
        path = (self.cleaned_data.get("backend_log_file_path") or "").strip()
        if not path:
            raise forms.ValidationError("Backend log file path is required.")
        if not PurePosixPath(path).is_absolute():
            raise forms.ValidationError(
                "Backend log file path must be absolute (for example /var/log/proxbox.log)."
            )
        if path.endswith("/"):
            raise forms.ValidationError(
                "Backend log file path must include a filename, not only a directory."
            )
        return path

    def clean(self) -> dict:
        """Cross-field validation for branching and intent-direction fields."""
        super().clean()
        enabled = self.cleaned_data.get("netbox_to_proxmox_enabled")
        phrase = (
            self.cleaned_data.get("netbox_to_proxmox_typed_confirmation") or ""
        ).strip()
        if enabled:
            if phrase != NETBOX_TO_PROXMOX_TYPED_PHRASE:
                self.add_error(
                    "netbox_to_proxmox_typed_confirmation",
                    forms.ValidationError(
                        "To enable NetBox → Proxmox writes you must type the exact "
                        f"phrase '{NETBOX_TO_PROXMOX_TYPED_PHRASE}'."
                    ),
                )
        else:
            self.cleaned_data["netbox_to_proxmox_typed_confirmation"] = ""
        return self.cleaned_data
