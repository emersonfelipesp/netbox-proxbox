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
_CONTROLLER_QS = models.ProxmoxSdnController.objects.select_related("endpoint")
_ZONE_QS = models.ProxmoxSdnZone.objects.select_related("endpoint")
_VNET_QS = models.ProxmoxSdnVNet.objects.select_related("endpoint", "l2vpn")
_SUBNET_QS = models.ProxmoxSdnSubnet.objects.select_related("endpoint", "prefix")
_BINDING_QS = models.ProxmoxSdnBinding.objects.select_related("endpoint")
_ROUTEMAP_QS = models.ProxmoxSdnRouteMap.objects.select_related("endpoint")
_PREFIXLIST_QS = models.ProxmoxSdnPrefixList.objects.select_related("endpoint")


# ── ProxmoxSdnFabric ─────────────────────────────────────────────────────────


@register_model_view(models.ProxmoxSdnFabric, "list", path="", detail=False)
class ProxmoxSdnFabricListView(ObjectListView):
    queryset = _FABRIC_QS
    table = tables.ProxmoxSdnFabricTable
    filterset = filtersets.ProxmoxSdnFabricFilterSet
    filterset_form = forms.ProxmoxSdnFabricFilterForm
    actions = {}


@register_model_view(models.ProxmoxSdnFabric)
class ProxmoxSdnFabricView(ObjectView):
    queryset = _FABRIC_QS


@register_model_view(models.ProxmoxSdnFabric, "add", detail=False)
@register_model_view(models.ProxmoxSdnFabric, "edit")
class ProxmoxSdnFabricEditView(ObjectEditView):
    queryset = _FABRIC_QS
    form = forms.ProxmoxSdnFabricForm


@register_model_view(models.ProxmoxSdnFabric, "delete")
class ProxmoxSdnFabricDeleteView(ObjectDeleteView):
    queryset = _FABRIC_QS


# ── ProxmoxSdnController ─────────────────────────────────────────────────────


@register_model_view(models.ProxmoxSdnController, "list", path="", detail=False)
class ProxmoxSdnControllerListView(ObjectListView):
    queryset = _CONTROLLER_QS
    table = tables.ProxmoxSdnControllerTable
    filterset = filtersets.ProxmoxSdnControllerFilterSet
    filterset_form = forms.ProxmoxSdnControllerFilterForm
    actions = {}


@register_model_view(models.ProxmoxSdnController)
class ProxmoxSdnControllerView(ObjectView):
    queryset = _CONTROLLER_QS


@register_model_view(models.ProxmoxSdnController, "add", detail=False)
@register_model_view(models.ProxmoxSdnController, "edit")
class ProxmoxSdnControllerEditView(ObjectEditView):
    queryset = _CONTROLLER_QS
    form = forms.ProxmoxSdnControllerForm


@register_model_view(models.ProxmoxSdnController, "delete")
class ProxmoxSdnControllerDeleteView(ObjectDeleteView):
    queryset = _CONTROLLER_QS


# ── ProxmoxSdnZone ───────────────────────────────────────────────────────────


@register_model_view(models.ProxmoxSdnZone, "list", path="", detail=False)
class ProxmoxSdnZoneListView(ObjectListView):
    queryset = _ZONE_QS
    table = tables.ProxmoxSdnZoneTable
    filterset = filtersets.ProxmoxSdnZoneFilterSet
    filterset_form = forms.ProxmoxSdnZoneFilterForm
    actions = {}


@register_model_view(models.ProxmoxSdnZone)
class ProxmoxSdnZoneView(ObjectView):
    queryset = _ZONE_QS


@register_model_view(models.ProxmoxSdnZone, "add", detail=False)
@register_model_view(models.ProxmoxSdnZone, "edit")
class ProxmoxSdnZoneEditView(ObjectEditView):
    queryset = _ZONE_QS
    form = forms.ProxmoxSdnZoneForm


@register_model_view(models.ProxmoxSdnZone, "delete")
class ProxmoxSdnZoneDeleteView(ObjectDeleteView):
    queryset = _ZONE_QS


# ── ProxmoxSdnVNet ───────────────────────────────────────────────────────────


@register_model_view(models.ProxmoxSdnVNet, "list", path="", detail=False)
class ProxmoxSdnVNetListView(ObjectListView):
    queryset = _VNET_QS
    table = tables.ProxmoxSdnVNetTable
    filterset = filtersets.ProxmoxSdnVNetFilterSet
    filterset_form = forms.ProxmoxSdnVNetFilterForm
    actions = {}


@register_model_view(models.ProxmoxSdnVNet)
class ProxmoxSdnVNetView(ObjectView):
    queryset = _VNET_QS


@register_model_view(models.ProxmoxSdnVNet, "add", detail=False)
@register_model_view(models.ProxmoxSdnVNet, "edit")
class ProxmoxSdnVNetEditView(ObjectEditView):
    queryset = _VNET_QS
    form = forms.ProxmoxSdnVNetForm


@register_model_view(models.ProxmoxSdnVNet, "delete")
class ProxmoxSdnVNetDeleteView(ObjectDeleteView):
    queryset = _VNET_QS


# ── ProxmoxSdnSubnet ─────────────────────────────────────────────────────────


@register_model_view(models.ProxmoxSdnSubnet, "list", path="", detail=False)
class ProxmoxSdnSubnetListView(ObjectListView):
    queryset = _SUBNET_QS
    table = tables.ProxmoxSdnSubnetTable
    filterset = filtersets.ProxmoxSdnSubnetFilterSet
    filterset_form = forms.ProxmoxSdnSubnetFilterForm
    actions = {}


@register_model_view(models.ProxmoxSdnSubnet)
class ProxmoxSdnSubnetView(ObjectView):
    queryset = _SUBNET_QS


@register_model_view(models.ProxmoxSdnSubnet, "add", detail=False)
@register_model_view(models.ProxmoxSdnSubnet, "edit")
class ProxmoxSdnSubnetEditView(ObjectEditView):
    queryset = _SUBNET_QS
    form = forms.ProxmoxSdnSubnetForm


@register_model_view(models.ProxmoxSdnSubnet, "delete")
class ProxmoxSdnSubnetDeleteView(ObjectDeleteView):
    queryset = _SUBNET_QS


# ── ProxmoxSdnBinding ────────────────────────────────────────────────────────


@register_model_view(models.ProxmoxSdnBinding, "list", path="", detail=False)
class ProxmoxSdnBindingListView(ObjectListView):
    queryset = _BINDING_QS
    table = tables.ProxmoxSdnBindingTable
    filterset = filtersets.ProxmoxSdnBindingFilterSet
    filterset_form = forms.ProxmoxSdnBindingFilterForm
    actions = {}


@register_model_view(models.ProxmoxSdnBinding)
class ProxmoxSdnBindingView(ObjectView):
    queryset = _BINDING_QS


@register_model_view(models.ProxmoxSdnBinding, "add", detail=False)
@register_model_view(models.ProxmoxSdnBinding, "edit")
class ProxmoxSdnBindingEditView(ObjectEditView):
    queryset = _BINDING_QS
    form = forms.ProxmoxSdnBindingForm


@register_model_view(models.ProxmoxSdnBinding, "delete")
class ProxmoxSdnBindingDeleteView(ObjectDeleteView):
    queryset = _BINDING_QS


# ── ProxmoxSdnRouteMap ───────────────────────────────────────────────────────


@register_model_view(models.ProxmoxSdnRouteMap, "list", path="", detail=False)
class ProxmoxSdnRouteMapListView(ObjectListView):
    queryset = _ROUTEMAP_QS
    table = tables.ProxmoxSdnRouteMapTable
    filterset = filtersets.ProxmoxSdnRouteMapFilterSet
    filterset_form = forms.ProxmoxSdnRouteMapFilterForm
    actions = {}


@register_model_view(models.ProxmoxSdnRouteMap)
class ProxmoxSdnRouteMapView(ObjectView):
    queryset = _ROUTEMAP_QS


@register_model_view(models.ProxmoxSdnRouteMap, "add", detail=False)
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
    actions = {}


@register_model_view(models.ProxmoxSdnPrefixList)
class ProxmoxSdnPrefixListView(ObjectView):
    queryset = _PREFIXLIST_QS


@register_model_view(models.ProxmoxSdnPrefixList, "add", detail=False)
@register_model_view(models.ProxmoxSdnPrefixList, "edit")
class ProxmoxSdnPrefixListEditView(ObjectEditView):
    queryset = _PREFIXLIST_QS
    form = forms.ProxmoxSdnPrefixListForm


@register_model_view(models.ProxmoxSdnPrefixList, "delete")
class ProxmoxSdnPrefixListDeleteView(ObjectDeleteView):
    queryset = _PREFIXLIST_QS
