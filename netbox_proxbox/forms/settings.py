"""Forms for plugin-level ProxBox settings."""

from pathlib import PurePosixPath

from django import forms

from netbox_proxbox.models.plugin_settings import DEFAULT_BACKEND_LOG_FILE_PATH


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
    vm_sync_max_concurrency = forms.IntegerField(
        required=True,
        min_value=1,
        max_value=64,
        initial=4,
        label="VM sync max concurrency",
        help_text="Maximum number of VMs synced in parallel during a full update.",
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
