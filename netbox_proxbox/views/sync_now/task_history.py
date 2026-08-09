"""Individual sync for VMTaskHistory."""

from django.contrib import messages
from django.http import HttpRequest
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views import View
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
    register_model_view,
)

from netbox_proxbox.models import VMTaskHistory
from netbox_proxbox.services.branch_lifecycle import get_active_branch_schema_id
from netbox_proxbox.services.individual_sync import sync_individual_with_dependencies
from netbox_proxbox.sync_params import _resolve_task_history_batch_params
from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync
from netbox_proxbox.views.sync_now import _handle_sync_response


@register_model_view(VMTaskHistory, "proxbox_sync_now", path="proxbox-sync-now")
class VMTaskHistorySyncNowView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST: sync a single VMTaskHistory entry from proxbox-api."""

    http_method_names = ["post"]

    def get_required_permission(self) -> str:
        """Return required permission."""
        return permission_enqueue_proxbox_sync()

    def post(self, request: HttpRequest, pk: int | str) -> HttpResponseRedirect:
        """Handle post."""
        task_history = get_object_or_404(
            VMTaskHistory.objects.restrict(request.user, "view"), pk=pk
        )

        params = _resolve_task_history_batch_params(task_history)
        if "error" in params:
            messages.error(
                request,
                _("Task history is missing the Proxmox context required for sync."),
            )
            return HttpResponseRedirect(task_history.get_absolute_url())

        response, status, dependencies = sync_individual_with_dependencies(
            params["path"],
            params["query_params"],
            netbox_branch_schema_id=get_active_branch_schema_id(),
        )

        return _handle_sync_response(
            request,
            response,
            status,
            dependencies,
            f"Task history '{task_history.upid}'",
            task_history.get_absolute_url(),
        )
