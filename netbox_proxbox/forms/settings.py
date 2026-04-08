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
