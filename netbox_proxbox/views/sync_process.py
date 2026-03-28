"""Provide NetBox CRUD views for sync process records."""

from netbox.views import generic
from utilities.views import register_model_view

from netbox_proxbox.filtersets import SyncProcessFilterSet
from netbox_proxbox.forms import SyncProcessFilterForm, SyncProcessForm
from netbox_proxbox.models import SyncProcess
from netbox_proxbox.tables import SyncProcessTable


__all__ = (
    "SyncProcessView",
    "SyncProcessListView",
    "SyncProcessEditView",
    "SyncProcessDeleteView",
)


@register_model_view(SyncProcess)
class SyncProcessView(generic.ObjectView):
    queryset = SyncProcess.objects.all()


@register_model_view(SyncProcess, "list", path="", detail=False)
class SyncProcessListView(generic.ObjectListView):
    queryset = SyncProcess.objects.all()
    table = SyncProcessTable
    filterset = SyncProcessFilterSet
    filterset_form = SyncProcessFilterForm


@register_model_view(SyncProcess, "edit")
class SyncProcessEditView(generic.ObjectEditView):
    queryset = SyncProcess.objects.all()
    form = SyncProcessForm


@register_model_view(SyncProcess, "delete")
class SyncProcessDeleteView(generic.ObjectDeleteView):
    queryset = SyncProcess.objects.all()
