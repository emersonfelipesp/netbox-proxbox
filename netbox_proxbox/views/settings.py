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
                "ssrf_protection_enabled": settings_obj.ssrf_protection_enabled,
                "allow_private_ips": settings_obj.allow_private_ips,
                "additional_allowed_ip_ranges": settings_obj.additional_allowed_ip_ranges,
                "explicitly_blocked_ip_ranges": settings_obj.explicitly_blocked_ip_ranges,
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
            settings_obj.save(
                update_fields=[
                    "use_guest_agent_interface_name",
                    "proxbox_fetch_max_concurrency",
                    "ignore_ipv6_link_local_addresses",
                    "ssrf_protection_enabled",
                    "allow_private_ips",
                    "additional_allowed_ip_ranges",
                    "explicitly_blocked_ip_ranges",
                ]
            )
            messages.success(request, "Proxbox plugin settings updated.")
            return redirect("plugins:netbox_proxbox:settings")
        return render(request, self.template_name, {"form": form})
