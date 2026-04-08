"""Persistent plugin-level settings for ProxBox behavior toggles."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel

DEFAULT_BACKEND_LOG_FILE_PATH = "/var/log/proxbox.log"


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
    backend_log_file_path = models.CharField(
        max_length=255,
        default=DEFAULT_BACKEND_LOG_FILE_PATH,
        verbose_name=_("Backend log file path"),
        help_text=_(
            "Absolute file path for proxbox-api rotated log archive output "
            "(for example /var/log/proxbox.log). Changes apply after proxbox-api restart."
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
