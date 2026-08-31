"""Dedicated page that hosts the Proxbox sync-state repair card."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View
from utilities.views import ConditionalLoginRequiredMixin

from netbox_proxbox.views.sync_state_repair import build_bootstrap_status_context

__all__ = ("SyncStateRepairPageView",)


class SyncStateRepairPageView(ConditionalLoginRequiredMixin, View):
    """Render the sync-state repair card on a page of its own.

    The card used to be inlined on the Proxbox home and settings pages. It is an
    operator recovery action rather than a routine one, so it now lives on its
    own page that is deliberately not registered in the plugin navigation; the
    only entry point is the link in the Proxbox home page footer.

    This view lives in its own module because ``sync_state_repair.py`` must not
    import ``ConditionalLoginRequiredMixin``: combining it with
    ``ContentTypePermissionRequiredMixin`` on the POST/AJAX views there produced
    an invalid MRO (commit 39f8f9d9), and a contract test pins that module free
    of the mixin.
    """

    template_name = "netbox_proxbox/sync_state_repair.html"

    def get(
        self, request: HttpRequest, *args: object, **kwargs: object
    ) -> HttpResponse:
        """Render the repair card with the shared bootstrap-status context."""
        return render(
            request,
            self.template_name,
            build_bootstrap_status_context(request, surface="repair"),
        )
