"""Quick-edit modal view for homepage endpoint cards."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View
from utilities.views import ConditionalLoginRequiredMixin

from netbox_proxbox.forms import (
    FastAPIEndpointForm,
    NetBoxEndpointForm,
    ProxmoxEndpointForm,
)
from netbox_proxbox.models import FastAPIEndpoint, NetBoxEndpoint, ProxmoxEndpoint

__all__ = ("HomeQuickEditView",)

_ENDPOINT_MAP: dict[
    str,
    tuple[type, type, str],
] = {
    "netbox": (NetBoxEndpoint, NetBoxEndpointForm, "change_netboxendpoint"),
    "proxmox": (ProxmoxEndpoint, ProxmoxEndpointForm, "change_proxmoxendpoint"),
    "fastapi": (FastAPIEndpoint, FastAPIEndpointForm, "change_fastapiendpoint"),
}

_FRAGMENT = "netbox_proxbox/home/quick_edit_form.html"


class HomeQuickEditView(ConditionalLoginRequiredMixin, View):
    """
    Serves the edit form for a single endpoint as an HTML fragment (GET) and
    processes the POST submission (returning JSON on success, re-rendered
    fragment with field errors on failure).

    URL: GET/POST /plugins/proxbox/quick-edit/<endpoint_type>/<pk>/
    """

    def _resolve(self, endpoint_type: str, pk: int, user):
        if endpoint_type not in _ENDPOINT_MAP:
            from django.http import Http404
            raise Http404(f"Unknown endpoint type: {endpoint_type!r}")
        model_cls, form_cls, _perm = _ENDPOINT_MAP[endpoint_type]
        obj = get_object_or_404(model_cls.objects.restrict(user, "change"), pk=pk)
        return obj, form_cls

    def get(self, request: HttpRequest, endpoint_type: str, pk: int) -> HttpResponse:
        obj, form_cls = self._resolve(endpoint_type, pk, request.user)
        form = form_cls(instance=obj)
        return render(
            request,
            _FRAGMENT,
            {"form": form, "object": obj, "endpoint_type": endpoint_type},
        )

    def post(self, request: HttpRequest, endpoint_type: str, pk: int) -> HttpResponse:
        obj, form_cls = self._resolve(endpoint_type, pk, request.user)
        form = form_cls(data=request.POST, files=request.FILES, instance=obj)
        if form.is_valid():
            form.save()
            return JsonResponse({"success": True, "name": str(obj)})
        return render(
            request,
            _FRAGMENT,
            {"form": form, "object": obj, "endpoint_type": endpoint_type},
            status=422,
        )
