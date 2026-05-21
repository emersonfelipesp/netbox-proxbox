"""NetBox CRUD views for Proxmox SDN models."""

from __future__ import annotations

from netbox.views.generic import (
    ObjectDeleteView,
    ObjectEditView,
    ObjectListView,
    ObjectView,
)
from utilities.views import register_model_view

from netbox_proxbox import filtersets, forms, models, tables

_FABRIC_QS = models.ProxmoxSdnFabric.objects.select_related("endpoint")
_ROUTEMAP_QS = models.ProxmoxSdnRouteMap.objects.select_related("endpoint")
_PREFIXLIST_QS = models.ProxmoxSdnPrefixList.objects.select_related("endpoint")


# ── ProxmoxSdnFabric ─────────────────────────────────────────────────────────


@register_model_view(models.ProxmoxSdnFabric, "list", path="", detail=False)
class ProxmoxSdnFabricListView(ObjectListView):
    queryset = _FABRIC_QS
    table = tables.ProxmoxSdnFabricTable
    filterset = filtersets.ProxmoxSdnFabricFilterSet
    filterset_form = forms.ProxmoxSdnFabricFilterForm


@register_model_view(models.ProxmoxSdnFabric)
class ProxmoxSdnFabricView(ObjectView):
    queryset = _FABRIC_QS


@register_model_view(models.ProxmoxSdnFabric, "edit")
class ProxmoxSdnFabricEditView(ObjectEditView):
    queryset = _FABRIC_QS
    form = forms.ProxmoxSdnFabricForm


@register_model_view(models.ProxmoxSdnFabric, "delete")
class ProxmoxSdnFabricDeleteView(ObjectDeleteView):
    queryset = _FABRIC_QS


# ── ProxmoxSdnRouteMap ───────────────────────────────────────────────────────


@register_model_view(models.ProxmoxSdnRouteMap, "list", path="", detail=False)
class ProxmoxSdnRouteMapListView(ObjectListView):
    queryset = _ROUTEMAP_QS
    table = tables.ProxmoxSdnRouteMapTable
    filterset = filtersets.ProxmoxSdnRouteMapFilterSet
    filterset_form = forms.ProxmoxSdnRouteMapFilterForm


@register_model_view(models.ProxmoxSdnRouteMap)
class ProxmoxSdnRouteMapView(ObjectView):
    queryset = _ROUTEMAP_QS


@register_model_view(models.ProxmoxSdnRouteMap, "edit")
class ProxmoxSdnRouteMapEditView(ObjectEditView):
    queryset = _ROUTEMAP_QS
    form = forms.ProxmoxSdnRouteMapForm


@register_model_view(models.ProxmoxSdnRouteMap, "delete")
class ProxmoxSdnRouteMapDeleteView(ObjectDeleteView):
    queryset = _ROUTEMAP_QS


# ── ProxmoxSdnPrefixList ─────────────────────────────────────────────────────


@register_model_view(models.ProxmoxSdnPrefixList, "list", path="", detail=False)
class ProxmoxSdnPrefixListListView(ObjectListView):
    queryset = _PREFIXLIST_QS
    table = tables.ProxmoxSdnPrefixListTable
    filterset = filtersets.ProxmoxSdnPrefixListFilterSet
    filterset_form = forms.ProxmoxSdnPrefixListFilterForm


@register_model_view(models.ProxmoxSdnPrefixList)
class ProxmoxSdnPrefixListView(ObjectView):
    queryset = _PREFIXLIST_QS


@register_model_view(models.ProxmoxSdnPrefixList, "edit")
class ProxmoxSdnPrefixListEditView(ObjectEditView):
    queryset = _PREFIXLIST_QS
    form = forms.ProxmoxSdnPrefixListForm


@register_model_view(models.ProxmoxSdnPrefixList, "delete")
class ProxmoxSdnPrefixListDeleteView(ObjectDeleteView):
    queryset = _PREFIXLIST_QS
