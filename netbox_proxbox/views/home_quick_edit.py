"""Quick-edit modal view for homepage endpoint cards."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.decorators.debug import sensitive_variables
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
        form = self._form(form_cls, obj, request.user)
        return render(
            request,
            _FRAGMENT,
            {"form": form, "object": obj, "endpoint_type": endpoint_type},
        )

    @staticmethod
    def _form(form_cls: type, obj: object, user: object, **kwargs: object):
        if form_cls is ProxmoxEndpointForm:
            kwargs["request_user"] = user
        return form_cls(instance=obj, **kwargs)

    def _submitted_form(self, request: HttpRequest, form_cls: type, obj: object):
        return self._form(
            form_cls,
            obj,
            request.user,
            data=request.POST,
            files=request.FILES,
        )

    def _save_fastapi_form(
        self,
        request: HttpRequest,
        form_cls: type,
        obj: FastAPIEndpoint,
    ) -> tuple[object, bool]:
        from django.db import transaction
        from netbox_proxbox.integrations.openbao_single_request import (
            single_secret_mutation_boundary,
        )

        with single_secret_mutation_boundary(
            [obj],
            [request.POST],
            model=FastAPIEndpoint,
            material_field="token",
            actor=request.user,
            request=request,
        ):
            with transaction.atomic():
                form = self._submitted_form(request, form_cls, obj)
                if not form.is_valid():
                    transaction.set_rollback(True)
                    return form, False
                form.save()
                return form, True

    def _save_regular_form(
        self, request: HttpRequest, form_cls: type, obj: object
    ) -> tuple[object, bool]:
        form = self._submitted_form(request, form_cls, obj)
        if not form.is_valid():
            return form, False
        form.save()
        return form, True

    @sensitive_variables()
    def post(self, request: HttpRequest, endpoint_type: str, pk: int) -> HttpResponse:
        obj, form_cls = self._resolve(endpoint_type, pk, request.user)
        if endpoint_type == "fastapi":
            form, saved = self._save_fastapi_form(request, form_cls, obj)
        else:
            form, saved = self._save_regular_form(request, form_cls, obj)
        if saved:
            return JsonResponse({"success": True, "name": str(obj)})
        return render(
            request,
            _FRAGMENT,
            {"form": form, "object": obj, "endpoint_type": endpoint_type},
            status=422,
        )
