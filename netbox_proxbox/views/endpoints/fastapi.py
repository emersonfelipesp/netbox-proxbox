"""Provide NetBox CRUD and OpenAPI tab views for FastAPI endpoint records."""

from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.decorators.debug import sensitive_variables
from netbox.api.authentication import TokenAuthentication
from netbox.views import generic
from utilities.permissions import get_permission_for_model
from utilities.query import reapply_model_ordering
from utilities.views import ViewTab, register_model_view

from netbox_proxbox.filtersets import FastAPIEndpointFilterSet
from netbox_proxbox.forms import (
    FastAPIEndpointFilterForm,
    FastAPIEndpointForm,
    FastAPIEndpointImportForm,
)
from netbox_proxbox.models import FastAPIEndpoint
from netbox_proxbox.services.openapi_schema import get_cached_openapi_schema
from netbox_proxbox.tables import FastAPIEndpointTable
from netbox_proxbox.views.endpoints.fastapi_export import (
    _fastapi_export_fieldnames,
    _serialize_fastapi_endpoint,
)


__all__ = (
    "FastAPIEndpointView",
    "FastAPIOpenAPIView",
    "FastAPIEndpointListView",
    "FastAPIEndpointBulkImportView",
    "FastAPIEndpointEditView",
    "FastAPIEndpointDeleteView",
    "FastAPIEndpointExportView",
    "FastAPIExportQuickAddTokenView",
)


@register_model_view(FastAPIEndpoint)
class FastAPIEndpointView(generic.ObjectView):
    """Detail view for a proxbox-api (FastAPI) backend endpoint."""

    queryset = FastAPIEndpoint.objects.all()


@register_model_view(FastAPIEndpoint, "openapi", path="openapi")
class FastAPIOpenAPIView(generic.ObjectView):
    """Detail tab that renders backend OpenAPI schema metadata and endpoints."""

    queryset = FastAPIEndpoint.objects.all()
    template_name = "netbox_proxbox/fastapiendpoint_openapi.html"
    tab = ViewTab(
        label="OpenAPI",
        permission="netbox_proxbox.view_fastapiendpoint",
        weight=1050,
    )

    def get_extra_context(
        self, request: HttpRequest, instance: FastAPIEndpoint
    ) -> dict[str, object]:
        """Return extra context."""
        force_refresh = str(request.GET.get("refresh", "")).strip().lower() in {
            "1",
            "true",
            "yes",
        }
        openapi_data = get_cached_openapi_schema(instance, force_refresh=force_refresh)
        return {
            "openapi_data": openapi_data,
            "openapi_force_refresh": force_refresh,
        }


@register_model_view(FastAPIEndpoint, "list", path="", detail=False)
class FastAPIEndpointListView(generic.ObjectListView):
    """Filterable list of FastAPI backend endpoint records."""

    queryset = FastAPIEndpoint.objects.all()
    table = FastAPIEndpointTable
    filterset = FastAPIEndpointFilterSet
    filterset_form = FastAPIEndpointFilterForm
    template_name = "netbox_proxbox/fastapiendpoint_list.html"
    actions = ()


@register_model_view(FastAPIEndpoint, "bulk_import", path="import", detail=False)
class FastAPIEndpointBulkImportView(generic.BulkImportView):
    """Bulk import FastAPI endpoints from structured data.

    FastAPIEndpoint is a singleton — at most one record is allowed. If an existing
    record is found during import, the user is prompted to confirm the override before
    the existing record is deleted and replaced with the imported data.

    An ``id`` column exported from another NetBox instance is silently discarded.
    """

    queryset = FastAPIEndpoint.objects.all()
    model_form = FastAPIEndpointImportForm

    @sensitive_variables()
    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """Intercept if singleton exists and override is not yet confirmed."""
        existing = FastAPIEndpoint.objects.first()
        if existing and request.POST.get("confirm_override") != "true":
            form = self.get_form()
            if form.is_valid():
                return render(
                    request,
                    "netbox_proxbox/singleton_import_confirm.html",
                    {
                        "existing": existing,
                        "model_name": FastAPIEndpoint._meta.verbose_name,
                        "import_url": request.path,
                        "return_url": reverse(
                            "plugins:netbox_proxbox:fastapiendpoint_list"
                        ),
                        "post_items": list(request.POST.lists()),
                    },
                )
        from netbox_proxbox.integrations.openbao_single_request import (
            single_secret_mutation_boundary,
        )

        owners = [existing] if existing is not None else []
        with single_secret_mutation_boundary(
            owners,
            [request.POST],
            model=FastAPIEndpoint,
            material_field="token",
            actor=request.user,
            request=request,
            allow_new=True,
        ):
            return super().post(request, *args, **kwargs)

    def create_and_update_objects(
        self, form: FastAPIEndpointImportForm, request: HttpRequest
    ) -> list[object]:
        """Strip exported ``id`` column and handle singleton replacement."""
        for record in form.cleaned_data.get("data", []):
            record.pop("id", None)

        if request.POST.get("confirm_override") == "true":
            existing = FastAPIEndpoint.objects.first()
            if existing:
                existing.delete()

        return super().create_and_update_objects(form, request)


@register_model_view(FastAPIEndpoint, "export", path="export", detail=False)
class FastAPIEndpointExportView(generic.ObjectListView):
    """Download filtered FastAPI endpoints as CSV, JSON, or YAML; secrets require token proof."""

    queryset = FastAPIEndpoint.objects.all()
    filterset = FastAPIEndpointFilterSet
    allowed_formats = {"csv", "json", "yaml"}

    def get_required_permission(self) -> str:
        """Require model ``view`` on FastAPI endpoints (same as the list)."""
        return get_permission_for_model(self.queryset.model, "view")

    def _v1_export_header(self, request: HttpRequest) -> str | None:
        from users.models import Token

        manual_token = (request.POST.get("v1_manual_token") or "").strip()
        if manual_token:
            return (
                manual_token
                if manual_token.startswith("Token ")
                else f"Token {manual_token}"
            )
        token_id = (request.POST.get("token_id") or "").strip()
        if not token_id:
            messages.error(
                request,
                "Select a v1 token or enter one manually to export secrets.",
            )
            return None
        try:
            token_obj = Token.objects.get(
                pk=int(token_id), version=1, user=request.user
            )
        except (Token.DoesNotExist, ValueError):
            messages.error(request, "The selected v1 token could not be found.")
            return None
        plaintext = (token_obj.plaintext or "").strip()
        if plaintext:
            return f"Token {plaintext}"
        messages.error(
            request,
            "The selected v1 token does not have a usable plaintext value.",
        )
        return None

    def _v2_export_header(self, request: HttpRequest) -> str | None:
        token_key = (request.POST.get("token_key") or "").strip()
        token_secret = (request.POST.get("token_secret") or "").strip()
        if token_key and token_secret:
            return f"Bearer {token_key}.{token_secret}"
        messages.error(
            request,
            "Both token key and token secret are required for v2 authentication.",
        )
        return None

    def _legacy_export_header(self, request: HttpRequest) -> str | None:
        raw_token = (request.POST.get("netbox_token") or "").strip()
        if not raw_token:
            messages.error(
                request, "A valid NetBox token is required to export secrets."
            )
            return None
        if raw_token.startswith(("Token ", "Bearer ")):
            return raw_token
        return (
            f"Bearer {raw_token}"
            if raw_token.startswith("nbt_")
            else f"Token {raw_token}"
        )

    def _sensitive_export_header(self, request: HttpRequest) -> str | None:
        token_version = (request.POST.get("token_version") or "").strip()
        if token_version == "v1":
            return self._v1_export_header(request)
        if token_version == "v2":
            return self._v2_export_header(request)
        return self._legacy_export_header(request)

    def _authenticate_export_user(
        self, request: HttpRequest, header_value: str
    ) -> Any | None:
        request.META["HTTP_AUTHORIZATION"] = header_value
        authenticator = TokenAuthentication()
        try:
            auth_result = authenticator.authenticate(request)
        except Exception:
            auth_result = None

        if not auth_result:
            messages.error(request, "The provided NetBox token is invalid.")
            return None

        user, _token = auth_result
        if not user.is_authenticated:
            messages.error(
                request, "The provided NetBox token could not be authenticated."
            )
            return None

        if not user.has_perm("netbox_proxbox.view_fastapiendpoint"):
            messages.error(
                request,
                "The provided token user does not have permission to view FastAPI endpoints.",
            )
            return None

        return user

    def _validate_sensitive_export_token(self, request: HttpRequest) -> Any | None:
        """Return the authenticated token user authorized for secret export."""
        header_value = self._sensitive_export_header(request)
        if header_value is None:
            return None
        return self._authenticate_export_user(request, header_value)

    def _resolve_export_format(self, request: HttpRequest) -> str:
        """Normalize ``format`` from GET/POST to one of ``allowed_formats`` (default csv)."""
        format_value = (
            request.GET.get("format") or request.POST.get("format") or "csv"
        ).lower()
        return format_value if format_value in self.allowed_formats else "csv"

    def _export_response(
        self,
        request: HttpRequest,
        include_sensitive: bool,
        data_format: str,
        *,
        material_user: Any = None,
    ) -> HttpResponse:
        """Serialize the current filtered queryset to a downloadable HTTP response."""
        import csv
        import io
        import json

        import yaml

        queryset = reapply_model_ordering(super().get_queryset(request))
        if self.filterset:
            queryset = self.filterset(request.GET, queryset, request=request).qs

        fieldnames = _fastapi_export_fieldnames(include_sensitive)
        rows = [
            _serialize_fastapi_endpoint(
                endpoint,
                include_sensitive,
                user=material_user,
            )
            for endpoint in queryset
        ]

        if data_format == "json":
            payload = json.dumps(rows, indent=2)
            response = HttpResponse(payload, content_type="application/json")
        elif data_format == "yaml":
            payload = yaml.safe_dump(rows, sort_keys=False)
            response = HttpResponse(payload, content_type="application/yaml")
        else:
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            response = HttpResponse(buffer.getvalue(), content_type="text/csv")

        suffix = "with-secrets" if include_sensitive else "safe"
        response["Content-Disposition"] = (
            f'attachment; filename="netbox_proxbox_fastapi_endpoints_{suffix}.{data_format}"'
        )
        return response

    def get(self, request: HttpRequest) -> HttpResponse:
        """Export without the backend token (safe columns only)."""
        data_format = self._resolve_export_format(request)
        return self._export_response(
            request,
            include_sensitive=False,
            data_format=data_format,
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        """Export with optional secrets after ``_validate_sensitive_export_token`` succeeds."""
        include_sensitive = request.POST.get("include_sensitive") == "true"
        data_format = self._resolve_export_format(request)
        material_user = None
        if include_sensitive:
            material_user = self._validate_sensitive_export_token(request)
            if material_user is None:
                return redirect("plugins:netbox_proxbox:fastapiendpoint_list")
        return self._export_response(
            request,
            include_sensitive=include_sensitive,
            data_format=data_format,
            material_user=material_user,
        )


@register_model_view(FastAPIEndpoint, "add", detail=False)
@register_model_view(FastAPIEndpoint, "edit")
class FastAPIEndpointEditView(generic.ObjectEditView):
    """Create or edit a FastAPI endpoint (URL, auth, and SSL options)."""

    queryset = FastAPIEndpoint.objects.all()
    form = FastAPIEndpointForm

    @sensitive_variables()
    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> object:
        """Own provider compensation outside NetBox's edit atomic block."""
        from netbox_proxbox.integrations.openbao_single_request import (
            single_secret_mutation_boundary,
        )

        owner = self.get_object(**kwargs)
        owners = [] if owner.pk is None else [owner]
        with single_secret_mutation_boundary(
            owners,
            [request.POST],
            model=FastAPIEndpoint,
            material_field="token",
            actor=request.user,
            request=request,
            allow_new=owner.pk is None,
        ):
            return super().post(request, *args, **kwargs)


@register_model_view(FastAPIEndpoint, "delete")
class FastAPIEndpointDeleteView(generic.ObjectDeleteView):
    """Delete a FastAPI endpoint record."""

    queryset = FastAPIEndpoint.objects.all()

    @sensitive_variables()
    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> object:
        """Own provider cleanup outside NetBox's deletion atomic block."""
        from netbox_proxbox.integrations.openbao_single_request import (
            single_secret_mutation_boundary,
        )

        owner = self.get_object(**kwargs)
        with single_secret_mutation_boundary(
            [owner],
            [],
            model=FastAPIEndpoint,
            material_field="token",
            actor=request.user,
            request=request,
        ):
            return super().post(request, *args, **kwargs)


@register_model_view(
    FastAPIEndpoint,
    "quick_add_token",
    path="export/quick-add-token",
    detail=False,
)
class FastAPIExportQuickAddTokenView(View):
    """Create a temporary v1 NetBox API token for use with the sensitive export modal.

    The token is created under the current user's account and its plaintext is returned
    once in the JSON response.  The UI warns the user to delete or securely store the
    token after the export is complete.
    """

    def post(self, request: HttpRequest) -> JsonResponse:
        from users.models import Token

        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required."}, status=401)

        if not request.user.has_perm("users.add_token"):
            return JsonResponse(
                {"error": "You do not have permission to create tokens."}, status=403
            )

        try:
            token = Token(version=1, user=request.user)
            token.full_clean()
            token.save()
        except Exception as exc:
            return JsonResponse({"error": f"Failed to create token: {exc}"}, status=500)

        return JsonResponse(
            {
                "id": token.pk,
                "display": str(token),
                "plaintext": token.plaintext,
            }
        )
