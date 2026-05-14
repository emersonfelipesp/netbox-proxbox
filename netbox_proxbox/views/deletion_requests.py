"""List, detail, approval, and rejection views for DeletionRequest records."""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from netbox.views import generic
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
    register_model_view,
)

from netbox_proxbox.forms import (
    DeletionRequestApproveForm,
    DeletionRequestRejectForm,
)
from netbox_proxbox.intent.deletion_executor import DeletionExecutorJob
from netbox_proxbox.models import DeletionRequest, ProxboxPluginSettings
from netbox_proxbox.tables.deletion_requests import DeletionRequestTable
from netbox_proxbox.views.proxbox_access import permission_authorize_deletion_request

__all__ = (
    "DeletionRequestApproveView",
    "DeletionRequestListView",
    "DeletionRequestRejectView",
    "DeletionRequestView",
)

SELF_APPROVAL_BLOCKED_MESSAGE = (
    "Self-approval blocked: a different authorized user must approve this request."
)


def _self_approval_allowed() -> bool:
    settings_obj = ProxboxPluginSettings.get_solo()
    return bool(settings_obj.intent_apply_authorization_self_approve_allowed)


def _deletion_request_queryset():
    return DeletionRequest.objects.select_related(
        "branch", "requested_by", "authorizer"
    )


def _visible_deletion_request(request: HttpRequest, pk: int | str) -> DeletionRequest:
    return get_object_or_404(
        _deletion_request_queryset().restrict(request.user, "view"),
        pk=pk,
    )


@register_model_view(DeletionRequest, "list", path="", detail=False)
class DeletionRequestListView(generic.ObjectListView):
    """Global list of deletion requests awaiting or recording authorization."""

    queryset = _deletion_request_queryset()
    table = DeletionRequestTable
    template_name = "netbox_proxbox/deletionrequest_list.html"
    actions = {
        "export": {"view"},
    }


@register_model_view(DeletionRequest)
class DeletionRequestView(generic.ObjectView):
    """Detail view for one safe-delete DeletionRequest."""

    queryset = _deletion_request_queryset()
    template_name = "netbox_proxbox/deletionrequest.html"


class _DeletionRequestAuthorizationMixin:
    """Require the custom four-eyes authorization permission."""

    def get_required_permission(self) -> str:
        return permission_authorize_deletion_request()


@register_model_view(DeletionRequest, "approve", path="approve")
class DeletionRequestApproveView(
    TokenConditionalLoginRequiredMixin,
    _DeletionRequestAuthorizationMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """Confirm VMID, approve the request, and enqueue executor RQ work."""

    http_method_names = ["get", "post"]
    template_name = "netbox_proxbox/deletionrequest_approve.html"

    def get(self, request: HttpRequest, pk: int | str) -> HttpResponse:
        deletion_request = _visible_deletion_request(request, pk)
        form = DeletionRequestApproveForm(instance=deletion_request)
        return render(
            request,
            self.template_name,
            {"object": deletion_request, "form": form},
        )

    def post(self, request: HttpRequest, pk: int | str) -> HttpResponse:
        deletion_request = _visible_deletion_request(request, pk)
        if (
            deletion_request.requested_by_id is not None
            and request.user.pk == deletion_request.requested_by_id
            and not _self_approval_allowed()
        ):
            return HttpResponseForbidden(SELF_APPROVAL_BLOCKED_MESSAGE)

        form = DeletionRequestApproveForm(request.POST, instance=deletion_request)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {"object": deletion_request, "form": form},
            )

        deletion_request.authorizer = request.user
        deletion_request.state = DeletionRequest.State.APPROVED
        deletion_request.approved_at = timezone.now()
        deletion_request.full_clean()
        deletion_request.save(update_fields=["authorizer", "state", "approved_at"])
        DeletionExecutorJob.enqueue(
            deletion_request_id=deletion_request.pk,
            user=request.user,
        )
        messages.success(request, _("Deletion request approved and queued."))
        return redirect(deletion_request.get_absolute_url())


@register_model_view(DeletionRequest, "reject", path="reject")
class DeletionRequestRejectView(
    TokenConditionalLoginRequiredMixin,
    _DeletionRequestAuthorizationMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """Reject a pending DeletionRequest with an operator-visible reason."""

    http_method_names = ["get", "post"]
    template_name = "netbox_proxbox/deletionrequest_reject.html"

    def get(self, request: HttpRequest, pk: int | str) -> HttpResponse:
        deletion_request = _visible_deletion_request(request, pk)
        form = DeletionRequestRejectForm()
        return render(
            request,
            self.template_name,
            {"object": deletion_request, "form": form},
        )

    def post(self, request: HttpRequest, pk: int | str) -> HttpResponse:
        deletion_request = _visible_deletion_request(request, pk)
        form = DeletionRequestRejectForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {"object": deletion_request, "form": form},
            )

        deletion_request.authorizer = request.user
        deletion_request.state = DeletionRequest.State.REJECTED
        deletion_request.reject_reason = form.cleaned_data["reject_reason"]
        deletion_request.save(update_fields=["authorizer", "state", "reject_reason"])
        messages.success(request, _("Deletion request rejected."))
        return redirect(deletion_request.get_absolute_url())
