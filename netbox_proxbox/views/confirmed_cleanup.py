"""Confirmation-aware cleanup wrappers for provider-owned deletion state."""

from __future__ import annotations

from typing import Any

from utilities.forms import BulkDeleteForm, DeleteForm
from utilities.jobs import is_background_request


class _DeleteIncomplete(Exception):
    """Carry a handled framework response while forcing outer rollback."""

    def __init__(self, response: Any) -> None:
        self.response = response


class ConfirmedCleanupDeleteMixin:
    """Run cleanup only for a valid single-object confirmation."""

    def cleanup_boundary(self, request: Any, objects: list[Any]):
        raise NotImplementedError

    def cleanup_objects(self, request: Any, objects: list[Any]) -> None:
        raise NotImplementedError

    def post(self, request: Any, *args: object, **kwargs: object) -> Any:
        instance = self.get_object(**kwargs)
        if not DeleteForm(request.POST, instance=instance).is_valid():
            return super().post(request, *args, **kwargs)
        return self._confirmed_delete(request, instance, args, kwargs)

    def _confirmed_delete(
        self,
        request: Any,
        instance: Any,
        args: tuple[object, ...],
        kwargs: dict[str, object],
    ) -> Any:
        primary_key = instance.pk
        try:
            with self.cleanup_boundary(request, [instance]):
                self.cleanup_objects(request, [instance])
                response = super().post(request, *args, **kwargs)
                if self.queryset.model.objects.filter(pk=primary_key).exists():
                    raise _DeleteIncomplete(response)
                return response
        except _DeleteIncomplete as exc:
            return exc.response


class ConfirmedCleanupBulkDeleteMixin:
    """Run cleanup only for a valid, executing bulk confirmation."""

    def cleanup_boundary(self, request: Any, objects: list[Any]):
        raise NotImplementedError

    def cleanup_objects(self, request: Any, objects: list[Any]) -> None:
        raise NotImplementedError

    def validate_cleanup_selection(self, request: Any, primary_keys: list[int]) -> None:
        del request, primary_keys

    def selected_cleanup_objects(
        self, request: Any, primary_keys: list[int]
    ) -> list[Any]:
        return list(
            self.get_queryset(request).filter(pk__in=primary_keys).order_by("pk")
        )

    def post(self, request: Any, **kwargs: object) -> Any:
        primary_keys = self._selected_primary_keys(request)
        self.validate_cleanup_selection(request, primary_keys)
        if not self._confirmed_for_execution(request):
            return super().post(request, **kwargs)
        objects = self.selected_cleanup_objects(request, primary_keys)
        return self._confirmed_bulk_delete(request, objects, kwargs)

    def _selected_primary_keys(self, request: Any) -> list[int]:
        if request.POST.get("_all"):
            queryset = self.queryset.model.objects.all()
            if self.filterset is not None:
                queryset = self.filterset(request.GET, queryset, request=request).qs
            return list(queryset.values_list("pk", flat=True))
        try:
            return [int(value) for value in request.POST.getlist("pk")]
        except (TypeError, ValueError):
            return []

    def _confirmed_for_execution(self, request: Any) -> bool:
        if "_confirm" not in request.POST:
            return False
        form = BulkDeleteForm(self.queryset.model, request.POST)
        if not form.is_valid():
            return False
        return is_background_request(request) or not form.cleaned_data["background_job"]

    def _confirmed_bulk_delete(
        self,
        request: Any,
        objects: list[Any],
        kwargs: dict[str, object],
    ) -> Any:
        object_ids = [instance.pk for instance in objects]
        try:
            with self.cleanup_boundary(request, objects):
                self.cleanup_objects(request, objects)
                response = super().post(request, **kwargs)
                remaining = self.queryset.model.objects.filter(pk__in=object_ids)
                if remaining.exists():
                    raise _DeleteIncomplete(response)
                return response
        except _DeleteIncomplete as exc:
            return exc.response
