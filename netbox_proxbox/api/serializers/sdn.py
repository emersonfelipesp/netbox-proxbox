"""API serializers for Proxmox SDN models."""

from __future__ import annotations

from netbox.api.fields import ChoiceField
from netbox.api.serializers import NetBoxModelSerializer

from netbox_proxbox.choices import FirewallSyncStatusChoices, SdnFabricTypeChoices
from netbox_proxbox.models import (
    ProxmoxSdnBinding,
    ProxmoxSdnController,
    ProxmoxSdnFabric,
    ProxmoxSdnPrefixList,
    ProxmoxSdnRouteMap,
    ProxmoxSdnSubnet,
    ProxmoxSdnVNet,
    ProxmoxSdnZone,
)


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


class ProxmoxSdnControllerSerializer(NetBoxModelSerializer):
    status = ChoiceField(choices=FirewallSyncStatusChoices, required=False)

    class Meta:
        model = ProxmoxSdnController
        fields = (
            "id",
            "url",
            "display",
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
            "custom_fields",
            "created",
            "last_updated",
        )


class ProxmoxSdnZoneSerializer(NetBoxModelSerializer):
    status = ChoiceField(choices=FirewallSyncStatusChoices, required=False)

    class Meta:
        model = ProxmoxSdnZone
        fields = (
            "id",
            "url",
            "display",
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
            "custom_fields",
            "created",
            "last_updated",
        )


class ProxmoxSdnVNetSerializer(NetBoxModelSerializer):
    status = ChoiceField(choices=FirewallSyncStatusChoices, required=False)

    class Meta:
        model = ProxmoxSdnVNet
        fields = (
            "id",
            "url",
            "display",
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
            "custom_fields",
            "created",
            "last_updated",
        )


class ProxmoxSdnSubnetSerializer(NetBoxModelSerializer):
    status = ChoiceField(choices=FirewallSyncStatusChoices, required=False)

    class Meta:
        model = ProxmoxSdnSubnet
        fields = (
            "id",
            "url",
            "display",
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
            "custom_fields",
            "created",
            "last_updated",
        )


class ProxmoxSdnBindingSerializer(NetBoxModelSerializer):
    class Meta:
        model = ProxmoxSdnBinding
        fields = (
            "id",
            "url",
            "display",
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
