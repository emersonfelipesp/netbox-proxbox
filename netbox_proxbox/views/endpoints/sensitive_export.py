"""Shared authorization and object scoping for explicit sensitive exports."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.db.models import QuerySet
from django.views.decorators.debug import sensitive_variables
from utilities.query import reapply_model_ordering

from netbox_proxbox.sensitive_data import require_sensitive_data_access

logger = logging.getLogger("netbox_proxbox.sensitive_export")


class CredentialSafeListMixin:
    """Do not pass credential-bearing model objects to arbitrary export templates."""

    def export_template(self, template: object, request: HttpRequest) -> HttpResponse:
        response = HttpResponse(
            "Custom credential export templates are unavailable. Use the endpoint export actions.",
            status=403,
        )
        response["Cache-Control"] = "no-store"
        return response

    def export_yaml(self) -> str:
        raise PermissionDenied("Use the endpoint export actions for safe YAML output.")


def selected_export_ids(request: HttpRequest) -> set[int]:
    """Reject malformed explicit selections rather than silently exporting a subset."""
    selected: set[int] = set()
    for data in (request.GET, request.POST):
        for name in ("id", "pk"):
            for raw_value in data.getlist(name):
                try:
                    selected.add(int(raw_value))
                except (TypeError, ValueError) as exc:
                    raise PermissionDenied("Invalid export selection.") from exc
    return selected


class SensitiveExportMixin:
    """Keep the session actor authoritative; tokens never replace that identity."""

    @sensitive_variables()
    def protected_export_response(
        self,
        request: HttpRequest,
        *,
        include_sensitive: bool,
        data_format: str,
        **kwargs: Any,
    ) -> HttpResponse:
        """Contain secret-bearing failures and record only fixed, non-secret fields."""
        if not include_sensitive:
            return self._export_response(
                request, include_sensitive=False, data_format=data_format, **kwargs
            )
        self._export_object_ids = ()
        correlation_id = str(uuid4())
        try:
            require_sensitive_data_access(request.user)
            response = self._export_response(
                request, include_sensitive=True, data_format=data_format, **kwargs
            )
            result = "success"
        except PermissionDenied:
            response = HttpResponse(
                "Sensitive data access is not authorized.", status=403
            )
            result = "denied"
        except Exception:
            # Provider/decryption errors can contain credentials. Never render or log them.
            response = HttpResponse("Sensitive export is unavailable.", status=503)
            result = "unavailable"
        response["Cache-Control"] = "no-store"
        response["X-Export-Correlation-ID"] = correlation_id
        logger.info(
            "Sensitive endpoint export result=%s actor_id=%s model=%s "
            "object_ids=%s format=%s correlation_id=%s",
            result,
            request.user.pk,
            self.queryset.model._meta.label_lower,
            self._export_object_ids,
            data_format if data_format in {"csv", "json", "yaml"} else "csv",
            correlation_id,
        )
        return response

    def authorized_export_queryset(
        self, request: HttpRequest, *, include_sensitive: bool
    ) -> QuerySet[Any]:
        if include_sensitive:
            require_sensitive_data_access(request.user)
        queryset = super().get_queryset(request).restrict(request.user, "view")
        selected = selected_export_ids(request)
        if selected:
            visible = set(queryset.filter(pk__in=selected).values_list("pk", flat=True))
            if include_sensitive:
                self._export_object_ids = tuple(sorted(visible))
            if visible != selected:
                raise PermissionDenied("Export selection is not authorized.")
            queryset = queryset.filter(pk__in=selected)
        if self.filterset:
            queryset = self.filterset(request.GET, queryset, request=request).qs
        if include_sensitive:
            self._export_object_ids = tuple(queryset.values_list("pk", flat=True))
        return reapply_model_ordering(queryset)
