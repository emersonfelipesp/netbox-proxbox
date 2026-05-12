"""Plugin settings page for feature toggles."""

import json

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views import View

from netbox_proxbox.constants import OVERWRITE_FIELD_GROUPS, OVERWRITE_FIELDS
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
        initial = {
            "use_guest_agent_interface_name": settings_obj.use_guest_agent_interface_name,
            "proxbox_fetch_max_concurrency": settings_obj.proxbox_fetch_max_concurrency,
            "ignore_ipv6_link_local_addresses": settings_obj.ignore_ipv6_link_local_addresses,
            "primary_ip_preference": settings_obj.primary_ip_preference,
            "netbox_max_concurrent": settings_obj.netbox_max_concurrent,
            "netbox_timeout": settings_obj.netbox_timeout,
            "netbox_write_concurrency": settings_obj.netbox_write_concurrency,
            "proxmox_fetch_concurrency": settings_obj.proxmox_fetch_concurrency,
            "netbox_max_retries": settings_obj.netbox_max_retries,
            "netbox_retry_delay": settings_obj.netbox_retry_delay,
            "netbox_get_cache_ttl": settings_obj.netbox_get_cache_ttl,
            "netbox_get_cache_max_entries": settings_obj.netbox_get_cache_max_entries,
            "netbox_get_cache_max_bytes": settings_obj.netbox_get_cache_max_bytes,
            "bulk_batch_size": settings_obj.bulk_batch_size,
            "bulk_batch_delay_ms": settings_obj.bulk_batch_delay_ms,
            "backup_batch_size": settings_obj.backup_batch_size,
            "backup_batch_delay_ms": settings_obj.backup_batch_delay_ms,
            "vm_sync_max_concurrency": settings_obj.vm_sync_max_concurrency,
            "custom_fields_request_delay": settings_obj.custom_fields_request_delay,
            "backend_log_file_path": settings_obj.backend_log_file_path,
            "debug_cache": settings_obj.debug_cache,
            "expose_internal_errors": settings_obj.expose_internal_errors,
            "ssrf_protection_enabled": settings_obj.ssrf_protection_enabled,
            "allow_private_ips": settings_obj.allow_private_ips,
            "additional_allowed_ip_ranges": settings_obj.additional_allowed_ip_ranges,
            "explicitly_blocked_ip_ranges": settings_obj.explicitly_blocked_ip_ranges,
            "encryption_enabled": bool(settings_obj.encryption_key),
            "proxmox_timeout": settings_obj.proxmox_timeout,
            "proxmox_max_retries": settings_obj.proxmox_max_retries,
            "proxmox_retry_backoff": settings_obj.proxmox_retry_backoff,
            "default_role_qemu": settings_obj.default_role_qemu_id,
            "default_role_lxc": settings_obj.default_role_lxc_id,
            "enable_tenant_name_regex": settings_obj.enable_tenant_name_regex,
            "tenant_name_regex_rules": json.dumps(
                settings_obj.tenant_name_regex_rules or [],
                indent=2,
            ),
            "branching_enabled": settings_obj.branching_enabled,
            "branch_name_prefix": settings_obj.branch_name_prefix,
            "branch_on_conflict": settings_obj.branch_on_conflict,
            "netbox_to_proxmox_enabled": settings_obj.netbox_to_proxmox_enabled,
            "netbox_to_proxmox_typed_confirmation": (
                settings_obj.netbox_to_proxmox_typed_confirmation
            ),
            "apply_destroy_confirmed": settings_obj.apply_destroy_confirmed,
        }
        for name in OVERWRITE_FIELDS:
            initial[name] = getattr(settings_obj, name)
        form = ProxboxPluginSettingsForm(initial=initial)
        return render(
            request,
            self.template_name,
            {"form": form, "overwrite_field_groups": OVERWRITE_FIELD_GROUPS},
        )

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
            settings_obj.netbox_timeout = form.cleaned_data["netbox_timeout"]
            settings_obj.netbox_write_concurrency = form.cleaned_data[
                "netbox_write_concurrency"
            ]
            settings_obj.proxmox_fetch_concurrency = form.cleaned_data[
                "proxmox_fetch_concurrency"
            ]
            settings_obj.netbox_max_retries = form.cleaned_data["netbox_max_retries"]
            settings_obj.netbox_retry_delay = form.cleaned_data["netbox_retry_delay"]
            settings_obj.netbox_get_cache_ttl = form.cleaned_data[
                "netbox_get_cache_ttl"
            ]
            settings_obj.netbox_get_cache_max_entries = form.cleaned_data[
                "netbox_get_cache_max_entries"
            ]
            settings_obj.netbox_get_cache_max_bytes = form.cleaned_data[
                "netbox_get_cache_max_bytes"
            ]
            settings_obj.bulk_batch_size = form.cleaned_data["bulk_batch_size"]
            settings_obj.bulk_batch_delay_ms = form.cleaned_data["bulk_batch_delay_ms"]
            settings_obj.backup_batch_size = form.cleaned_data["backup_batch_size"]
            settings_obj.backup_batch_delay_ms = form.cleaned_data[
                "backup_batch_delay_ms"
            ]
            settings_obj.vm_sync_max_concurrency = form.cleaned_data[
                "vm_sync_max_concurrency"
            ]
            settings_obj.custom_fields_request_delay = form.cleaned_data.get(
                "custom_fields_request_delay", 0
            )
            settings_obj.debug_cache = form.cleaned_data.get("debug_cache", False)
            settings_obj.expose_internal_errors = form.cleaned_data.get(
                "expose_internal_errors", False
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
            settings_obj.default_role_qemu = form.cleaned_data.get("default_role_qemu")
            settings_obj.default_role_lxc = form.cleaned_data.get("default_role_lxc")
            settings_obj.enable_tenant_name_regex = form.cleaned_data.get(
                "enable_tenant_name_regex", False
            )
            settings_obj.tenant_name_regex_rules = form.cleaned_data.get(
                "tenant_name_regex_rules", []
            )
            settings_obj.branching_enabled = form.cleaned_data.get(
                "branching_enabled", False
            )
            settings_obj.branch_name_prefix = form.cleaned_data.get(
                "branch_name_prefix", "proxbox-sync"
            )
            settings_obj.branch_on_conflict = form.cleaned_data.get(
                "branch_on_conflict", "fail"
            )
            settings_obj.netbox_to_proxmox_enabled = form.cleaned_data.get(
                "netbox_to_proxmox_enabled", False
            )
            settings_obj.netbox_to_proxmox_typed_confirmation = form.cleaned_data.get(
                "netbox_to_proxmox_typed_confirmation", ""
            )
            settings_obj.apply_destroy_confirmed = form.cleaned_data.get(
                "apply_destroy_confirmed", False
            )
            for _overwrite_field in OVERWRITE_FIELDS:
                setattr(
                    settings_obj,
                    _overwrite_field,
                    form.cleaned_data.get(_overwrite_field, True),
                )
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
                    "netbox_timeout",
                    "netbox_write_concurrency",
                    "proxmox_fetch_concurrency",
                    "netbox_max_retries",
                    "netbox_retry_delay",
                    "netbox_get_cache_ttl",
                    "netbox_get_cache_max_entries",
                    "netbox_get_cache_max_bytes",
                    "bulk_batch_size",
                    "bulk_batch_delay_ms",
                    "backup_batch_size",
                    "backup_batch_delay_ms",
                    "vm_sync_max_concurrency",
                    "custom_fields_request_delay",
                    "backend_log_file_path",
                    "debug_cache",
                    "expose_internal_errors",
                    "ssrf_protection_enabled",
                    "allow_private_ips",
                    "additional_allowed_ip_ranges",
                    "explicitly_blocked_ip_ranges",
                    "encryption_key",
                    "proxmox_timeout",
                    "proxmox_max_retries",
                    "proxmox_retry_backoff",
                    "default_role_qemu",
                    "default_role_lxc",
                    "enable_tenant_name_regex",
                    "tenant_name_regex_rules",
                    "branching_enabled",
                    "branch_name_prefix",
                    "branch_on_conflict",
                    "netbox_to_proxmox_enabled",
                    "netbox_to_proxmox_typed_confirmation",
                    "apply_destroy_confirmed",
                    *OVERWRITE_FIELDS,
                ]
            )
            messages.success(request, "Proxbox plugin settings updated.")
            return redirect("plugins:netbox_proxbox:settings")
        return render(
            request,
            self.template_name,
            {"form": form, "overwrite_field_groups": OVERWRITE_FIELD_GROUPS},
        )
