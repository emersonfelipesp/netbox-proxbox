"""NetBox CRUD views for Proxmox datacenter models."""

from __future__ import annotations

from netbox.views.generic import (
    ObjectDeleteView,
    ObjectEditView,
    ObjectListView,
    ObjectView,
)
from utilities.views import register_model_view

from netbox_proxbox import filtersets, forms, models, tables

_CPU_QS = models.ProxmoxDatacenterCpuModel.objects.select_related("endpoint")


# ── ProxmoxDatacenterCpuModel ────────────────────────────────────────────────


@register_model_view(models.ProxmoxDatacenterCpuModel, "list", path="", detail=False)
class ProxmoxDatacenterCpuModelListView(ObjectListView):
    queryset = _CPU_QS
    table = tables.ProxmoxDatacenterCpuModelTable
    filterset = filtersets.ProxmoxDatacenterCpuModelFilterSet
    filterset_form = forms.ProxmoxDatacenterCpuModelFilterForm
    actions = {}


@register_model_view(models.ProxmoxDatacenterCpuModel)
class ProxmoxDatacenterCpuModelView(ObjectView):
    queryset = _CPU_QS


@register_model_view(models.ProxmoxDatacenterCpuModel, "add", detail=False)
@register_model_view(models.ProxmoxDatacenterCpuModel, "edit")
class ProxmoxDatacenterCpuModelEditView(ObjectEditView):
    queryset = _CPU_QS
    form = forms.ProxmoxDatacenterCpuModelForm


@register_model_view(models.ProxmoxDatacenterCpuModel, "delete")
class ProxmoxDatacenterCpuModelDeleteView(ObjectDeleteView):
    queryset = _CPU_QS
