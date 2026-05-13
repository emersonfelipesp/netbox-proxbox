"""Views for netbox-pbs.

PR C1 ships only a placeholder home view so the plugin can boot, register
its URL namespace, and render a navigation entry. Real list/detail views
land in PR C2 alongside the PBS domain models.
"""

from django.views.generic import TemplateView

from utilities.views import ConditionalLoginRequiredMixin


class PBSHomeView(ConditionalLoginRequiredMixin, TemplateView):
    """Placeholder home page for the netbox-pbs plugin."""

    template_name = "netbox_pbs/home.html"
