"""Confirmation-aware cleanup wrappers for provider-owned deletion state."""

from __future__ import annotations

from typing import Any

from core.signals import clear_events
from django.db import router, transaction
from utilities.forms import BulkDeleteForm, DeleteForm
from utilities.jobs import is_background_request


class _DeleteIncomplete(Exception):
    """Carry a handled framework response while forcing outer rollback."""

    def __init__(self, response: Any) -> None:
        self.response = response


def _discard_rolled_back_events(sender: Any) -> None:
    """Drop change events queued by a delete whose transaction rolled back.

    NetBox 4.7 clears the request's event queue after a refused delete, but 4.5
    and 4.6 do not. The cleanup boundary has rolled back every change in the
    request, so no queued event may reach webhooks, scripts or event rules.
    """
    clear_events.send(sender=sender)


def _delete_in_savepoint(instance: Any) -> None:
    """Give the framework's single-object delete its own savepoint.

    NetBox 4.7 deletes inside ``transaction.atomic()``, while 4.5 and 4.6 call
    ``obj.delete()`` directly. Django's deletion collector runs in an atomic
    block without a savepoint, so a protected or restricted refusal would mark
    the surrounding cleanup transaction for rollback. The framework's refusal
    handler would then fail on its next query with TransactionManagementError
    and answer HTTP 500 instead of refusing the delete.
    """
    delete = instance.delete
    using = router.db_for_write(type(instance), instance=instance)

    def delete_in_savepoint(*args: Any, **kwargs: Any) -> Any:
        with transaction.atomic(using=using):
            return delete(*args, **kwargs)

    instance.delete = delete_in_savepoint


class ConfirmedCleanupDeleteMixin:
    """Run cleanup only for a valid single-object confirmation."""

    _savepoint_framework_delete = False

    def get_object(self, **kwargs: object) -> Any:
        instance = super().get_object(**kwargs)
        if self._savepoint_framework_delete:
            _delete_in_savepoint(instance)
        return instance

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
        self._savepoint_framework_delete = True
        try:
            with self.cleanup_boundary(request, [instance]):
                self.cleanup_objects(request, [instance])
                response = super().post(request, *args, **kwargs)
                if self.queryset.model.objects.filter(pk=primary_key).exists():
                    raise _DeleteIncomplete(response)
                return response
        except _DeleteIncomplete as exc:
            _discard_rolled_back_events(self)
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
            _discard_rolled_back_events(self)
            return exc.response
