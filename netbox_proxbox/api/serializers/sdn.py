"""API serializers for Proxmox SDN models."""

from __future__ import annotations

from netbox.api.fields import ChoiceField
from netbox.api.serializers import NetBoxModelSerializer

from netbox_proxbox.choices import FirewallSyncStatusChoices, SdnFabricTypeChoices
from netbox_proxbox.models import ProxmoxSdnFabric, ProxmoxSdnPrefixList, ProxmoxSdnRouteMap


class ProxmoxSdnFabricSerializer(NetBoxModelSerializer):
    fabric_type = ChoiceField(choices=SdnFabricTypeChoices, required=False)
    status = ChoiceField(choices=FirewallSyncStatusChoices, required=False)

    class Meta:
        model = ProxmoxSdnFabric
        fields = (
            "id",
            "url",
            "display",
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
            "custom_fields",
            "created",
            "last_updated",
        )


class ProxmoxSdnRouteMapSerializer(NetBoxModelSerializer):
    status = ChoiceField(choices=FirewallSyncStatusChoices, required=False)

    class Meta:
        model = ProxmoxSdnRouteMap
        fields = (
            "id",
            "url",
            "display",
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
            "custom_fields",
            "created",
            "last_updated",
        )


class ProxmoxSdnPrefixListSerializer(NetBoxModelSerializer):
    status = ChoiceField(choices=FirewallSyncStatusChoices, required=False)

    class Meta:
        model = ProxmoxSdnPrefixList
        fields = (
            "id",
            "url",
            "display",
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
            "custom_fields",
            "created",
            "last_updated",
        )
