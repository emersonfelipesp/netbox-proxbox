"""Plugin settings page for feature toggles."""

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views import View

from netbox_proxbox.forms.settings import ProxboxPluginSettingsForm
from netbox_proxbox.models import ProxboxPluginSettings
from netbox_proxbox.views.proxbox_access import (
    permission_change_proxbox_plugin_settings,
)
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
)


class SettingsView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """Render and persist plugin-level operational settings."""

    template_name = "netbox_proxbox/settings.html"

    def get_required_permission(self) -> str:
        """Return required permission."""
        return permission_change_proxbox_plugin_settings()

    def get(self, request: HttpRequest) -> HttpResponse:
        """Handle get."""
        settings_obj = ProxboxPluginSettings.get_solo()
        form = ProxboxPluginSettingsForm(
            initial={
                "use_guest_agent_interface_name": settings_obj.use_guest_agent_interface_name,
                "proxbox_fetch_max_concurrency": settings_obj.proxbox_fetch_max_concurrency,
                "ignore_ipv6_link_local_addresses": settings_obj.ignore_ipv6_link_local_addresses,
                "primary_ip_preference": settings_obj.primary_ip_preference,
                "netbox_max_concurrent": settings_obj.netbox_max_concurrent,
                "netbox_max_retries": settings_obj.netbox_max_retries,
                "netbox_retry_delay": settings_obj.netbox_retry_delay,
                "netbox_get_cache_ttl": settings_obj.netbox_get_cache_ttl,
                "bulk_batch_size": settings_obj.bulk_batch_size,
                "bulk_batch_delay_ms": settings_obj.bulk_batch_delay_ms,
                "vm_sync_max_concurrency": settings_obj.vm_sync_max_concurrency,
                "custom_fields_request_delay": settings_obj.custom_fields_request_delay,
                "backend_log_file_path": settings_obj.backend_log_file_path,
                "ssrf_protection_enabled": settings_obj.ssrf_protection_enabled,
                "allow_private_ips": settings_obj.allow_private_ips,
                "additional_allowed_ip_ranges": settings_obj.additional_allowed_ip_ranges,
                "explicitly_blocked_ip_ranges": settings_obj.explicitly_blocked_ip_ranges,
                "encryption_enabled": bool(settings_obj.encryption_key),
                "proxmox_timeout": settings_obj.proxmox_timeout,
                "proxmox_max_retries": settings_obj.proxmox_max_retries,
                "proxmox_retry_backoff": settings_obj.proxmox_retry_backoff,
            }
        )
        return render(request, self.template_name, {"form": form})

    def post(self, request: HttpRequest) -> HttpResponse:
        """Handle post."""
        settings_obj = ProxboxPluginSettings.get_solo()
        form = ProxboxPluginSettingsForm(request.POST)
        if form.is_valid():
            settings_obj.use_guest_agent_interface_name = form.cleaned_data[
                "use_guest_agent_interface_name"
            ]
            settings_obj.proxbox_fetch_max_concurrency = form.cleaned_data[
                "proxbox_fetch_max_concurrency"
            ]
            settings_obj.ignore_ipv6_link_local_addresses = form.cleaned_data[
                "ignore_ipv6_link_local_addresses"
            ]
            settings_obj.primary_ip_preference = form.cleaned_data[
                "primary_ip_preference"
            ]
            settings_obj.backend_log_file_path = form.cleaned_data[
                "backend_log_file_path"
            ]
            settings_obj.ssrf_protection_enabled = form.cleaned_data.get(
                "ssrf_protection_enabled", False
            )
            settings_obj.allow_private_ips = form.cleaned_data.get(
                "allow_private_ips", False
            )
            settings_obj.additional_allowed_ip_ranges = form.cleaned_data.get(
                "additional_allowed_ip_ranges", ""
            )
            settings_obj.explicitly_blocked_ip_ranges = form.cleaned_data.get(
                "explicitly_blocked_ip_ranges", ""
            )
            settings_obj.use_guest_agent_interface_name = form.cleaned_data[
                "use_guest_agent_interface_name"
            ]
            settings_obj.proxbox_fetch_max_concurrency = form.cleaned_data[
                "proxbox_fetch_max_concurrency"
            ]
            settings_obj.ignore_ipv6_link_local_addresses = form.cleaned_data[
                "ignore_ipv6_link_local_addresses"
            ]
            settings_obj.primary_ip_preference = form.cleaned_data[
                "primary_ip_preference"
            ]
            settings_obj.netbox_max_concurrent = form.cleaned_data[
                "netbox_max_concurrent"
            ]
            settings_obj.netbox_max_retries = form.cleaned_data["netbox_max_retries"]
            settings_obj.netbox_retry_delay = form.cleaned_data["netbox_retry_delay"]
            settings_obj.netbox_get_cache_ttl = form.cleaned_data[
                "netbox_get_cache_ttl"
            ]
            settings_obj.bulk_batch_size = form.cleaned_data["bulk_batch_size"]
            settings_obj.bulk_batch_delay_ms = form.cleaned_data["bulk_batch_delay_ms"]
            settings_obj.vm_sync_max_concurrency = form.cleaned_data[
                "vm_sync_max_concurrency"
            ]
            settings_obj.custom_fields_request_delay = form.cleaned_data.get(
                "custom_fields_request_delay", 0
            )
            settings_obj.backend_log_file_path = form.cleaned_data[
                "backend_log_file_path"
            ]
            settings_obj.ssrf_protection_enabled = form.cleaned_data.get(
                "ssrf_protection_enabled", False
            )
            settings_obj.allow_private_ips = form.cleaned_data.get(
                "allow_private_ips", False
            )
            settings_obj.additional_allowed_ip_ranges = form.cleaned_data.get(
                "additional_allowed_ip_ranges", ""
            )
            settings_obj.explicitly_blocked_ip_ranges = form.cleaned_data.get(
                "explicitly_blocked_ip_ranges", ""
            )
            settings_obj.proxmox_timeout = form.cleaned_data["proxmox_timeout"]
            settings_obj.proxmox_max_retries = form.cleaned_data["proxmox_max_retries"]
            settings_obj.proxmox_retry_backoff = form.cleaned_data[
                "proxmox_retry_backoff"
            ]
            encryption_enabled = form.cleaned_data.get("encryption_enabled", False)
            if encryption_enabled:
                new_key = form.cleaned_data.get("encryption_key", "").strip()
                if new_key:
                    settings_obj.encryption_key = new_key
                # If checked but key field is blank, preserve existing key
            else:
                settings_obj.encryption_key = ""
            settings_obj.save(
                update_fields=[
                    "use_guest_agent_interface_name",
                    "proxbox_fetch_max_concurrency",
                    "ignore_ipv6_link_local_addresses",
                    "primary_ip_preference",
                    "netbox_max_concurrent",
                    "netbox_max_retries",
                    "netbox_retry_delay",
                    "netbox_get_cache_ttl",
                    "bulk_batch_size",
                    "bulk_batch_delay_ms",
                    "vm_sync_max_concurrency",
                    "custom_fields_request_delay",
                    "backend_log_file_path",
                    "ssrf_protection_enabled",
                    "allow_private_ips",
                    "additional_allowed_ip_ranges",
                    "explicitly_blocked_ip_ranges",
                    "encryption_key",
                    "proxmox_timeout",
                    "proxmox_max_retries",
                    "proxmox_retry_backoff",
                ]
            )
            messages.success(request, "Proxbox plugin settings updated.")
            return redirect("plugins:netbox_proxbox:settings")
        return render(request, self.template_name, {"form": form})
