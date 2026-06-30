"""Create/edit and filter forms for Proxmox SDN models."""

from __future__ import annotations

from django import forms
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from utilities.forms.fields import DynamicModelChoiceField

from netbox_proxbox import models
from netbox_proxbox.choices import FirewallSyncStatusChoices, SdnFabricTypeChoices


def _choices_2tuple(choice_set):
    return [(value, label) for value, label, *_ in choice_set.CHOICES]


_STATUS_CHOICES = [("", "---------")] + _choices_2tuple(FirewallSyncStatusChoices)
_FABRIC_TYPE_CHOICES = [("", "---------")] + _choices_2tuple(SdnFabricTypeChoices)


class _SdnEndpointMixin:
    endpoint = DynamicModelChoiceField(
        queryset=models.ProxmoxEndpoint.objects.all(),
        required=False,
    )


class ProxmoxSdnFabricForm(_SdnEndpointMixin, NetBoxModelForm):
    class Meta:
        model = models.ProxmoxSdnFabric
        fields = (
            "endpoint",
            "cluster_name",
            "fabric_name",
            "fabric_type",
            "asn",
            "advertise_subnets",
            "disable_arp_nd_suppression",
            "vrf_vxlan",
            "peers",
            "status",
            "raw_config",
            "tags",
        )


class ProxmoxSdnFabricFilterForm(_SdnEndpointMixin, NetBoxModelFilterSetForm):
    model = models.ProxmoxSdnFabric
    fabric_type = forms.ChoiceField(choices=_FABRIC_TYPE_CHOICES, required=False)
    status = forms.ChoiceField(choices=_STATUS_CHOICES, required=False)


class ProxmoxSdnControllerForm(_SdnEndpointMixin, NetBoxModelForm):
    class Meta:
        model = models.ProxmoxSdnController
        fields = (
            "endpoint",
            "cluster_name",
            "controller_name",
            "controller_type",
            "asn",
            "peers",
            "nodes",
            "loopback",
            "state",
            "status",
            "raw_config",
            "tags",
        )


class ProxmoxSdnControllerFilterForm(_SdnEndpointMixin, NetBoxModelFilterSetForm):
    model = models.ProxmoxSdnController
    status = forms.ChoiceField(choices=_STATUS_CHOICES, required=False)


class ProxmoxSdnZoneForm(_SdnEndpointMixin, NetBoxModelForm):
    class Meta:
        model = models.ProxmoxSdnZone
        fields = (
            "endpoint",
            "cluster_name",
            "zone_name",
            "zone_type",
            "controller",
            "vrf_vxlan",
            "tag",
            "mtu",
            "dns",
            "ipam",
            "rt_import",
            "state",
            "status",
            "raw_config",
            "tags",
        )


class ProxmoxSdnZoneFilterForm(_SdnEndpointMixin, NetBoxModelFilterSetForm):
    model = models.ProxmoxSdnZone
    status = forms.ChoiceField(choices=_STATUS_CHOICES, required=False)


class ProxmoxSdnVNetForm(_SdnEndpointMixin, NetBoxModelForm):
    class Meta:
        model = models.ProxmoxSdnVNet
        fields = (
            "endpoint",
            "cluster_name",
            "zone_name",
            "vnet_name",
            "vnet_type",
            "tag",
            "alias",
            "vlanaware",
            "state",
            "l2vpn",
            "status",
            "raw_config",
            "tags",
        )


class ProxmoxSdnVNetFilterForm(_SdnEndpointMixin, NetBoxModelFilterSetForm):
    model = models.ProxmoxSdnVNet
    status = forms.ChoiceField(choices=_STATUS_CHOICES, required=False)


class ProxmoxSdnSubnetForm(_SdnEndpointMixin, NetBoxModelForm):
    class Meta:
        model = models.ProxmoxSdnSubnet
        fields = (
            "endpoint",
            "cluster_name",
            "zone_name",
            "vnet_name",
            "subnet",
            "subnet_type",
            "gateway",
            "snat",
            "prefix",
            "skip_reason",
            "status",
            "raw_config",
            "tags",
        )


class ProxmoxSdnSubnetFilterForm(_SdnEndpointMixin, NetBoxModelFilterSetForm):
    model = models.ProxmoxSdnSubnet
    status = forms.ChoiceField(choices=_STATUS_CHOICES, required=False)


class ProxmoxSdnBindingForm(_SdnEndpointMixin, NetBoxModelForm):
    class Meta:
        model = models.ProxmoxSdnBinding
        fields = (
            "endpoint",
            "cluster_name",
            "source_type",
            "source_name",
            "node",
            "zone_name",
            "vnet_name",
            "target_type",
            "target_id",
            "status",
            "conflict_reason",
            "raw_config",
            "tags",
        )


class ProxmoxSdnBindingFilterForm(_SdnEndpointMixin, NetBoxModelFilterSetForm):
    model = models.ProxmoxSdnBinding


class ProxmoxSdnRouteMapForm(_SdnEndpointMixin, NetBoxModelForm):
    class Meta:
        model = models.ProxmoxSdnRouteMap
        fields = (
            "endpoint",
            "cluster_name",
            "name",
            "action",
            "match_peer",
            "match_ip",
            "set_community",
            "order",
            "status",
            "raw_config",
            "tags",
        )


class ProxmoxSdnRouteMapFilterForm(_SdnEndpointMixin, NetBoxModelFilterSetForm):
    model = models.ProxmoxSdnRouteMap
    status = forms.ChoiceField(choices=_STATUS_CHOICES, required=False)


class ProxmoxSdnPrefixListForm(_SdnEndpointMixin, NetBoxModelForm):
    class Meta:
        model = models.ProxmoxSdnPrefixList
        fields = (
            "endpoint",
            "cluster_name",
            "name",
            "cidr",
            "action",
            "le",
            "ge",
            "status",
            "raw_config",
            "tags",
        )


class ProxmoxSdnPrefixListFilterForm(_SdnEndpointMixin, NetBoxModelFilterSetForm):
    model = models.ProxmoxSdnPrefixList
    status = forms.ChoiceField(choices=_STATUS_CHOICES, required=False)
