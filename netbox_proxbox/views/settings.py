"""Plugin settings page for feature toggles."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views import View

from netbox_proxbox.forms.settings import ProxboxPluginSettingsForm
from netbox_proxbox.models import ProxboxPluginSettings
from netbox_proxbox.views.proxbox_access import permission_change_proxbox_plugin_settings
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

    def get_required_permission(self):
        return permission_change_proxbox_plugin_settings()

    def get(self, request):
        settings_obj = ProxboxPluginSettings.get_solo()
        form = ProxboxPluginSettingsForm(
            initial={
                "use_guest_agent_interface_name": settings_obj.use_guest_agent_interface_name
            }
        )
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        settings_obj = ProxboxPluginSettings.get_solo()
        form = ProxboxPluginSettingsForm(request.POST)
        if form.is_valid():
            settings_obj.use_guest_agent_interface_name = form.cleaned_data[
                "use_guest_agent_interface_name"
            ]
            settings_obj.save(update_fields=["use_guest_agent_interface_name"])
            messages.success(request, "Proxbox plugin settings updated.")
            return redirect("plugins:netbox_proxbox:settings")
        return render(request, self.template_name, {"form": form})
