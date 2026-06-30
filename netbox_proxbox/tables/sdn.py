"""Tables for Proxmox SDN models."""

from __future__ import annotations

import django_tables2 as tables
from netbox.tables import NetBoxTable, columns

from netbox_proxbox import models


class ProxmoxSdnFabricTable(NetBoxTable):
    fabric_name = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)
    fabric_type = columns.ChoiceFieldColumn()
    status = columns.ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.ProxmoxSdnFabric
        fields = (
            "pk",
            "id",
            "fabric_name",
            "cluster_name",
            "endpoint",
            "fabric_type",
            "asn",
            "status",
            "tags",
            "created",
            "last_updated",
        )
        default_columns = (
            "fabric_name",
            "cluster_name",
            "endpoint",
            "fabric_type",
            "asn",
            "status",
        )


class ProxmoxSdnControllerTable(NetBoxTable):
    controller_name = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)
    status = columns.ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.ProxmoxSdnController
        fields = (
            "pk",
            "id",
            "controller_name",
            "cluster_name",
            "endpoint",
            "controller_type",
            "asn",
            "status",
            "tags",
            "created",
            "last_updated",
        )
        default_columns = (
            "controller_name",
            "cluster_name",
            "endpoint",
            "controller_type",
            "asn",
            "status",
        )


class ProxmoxSdnZoneTable(NetBoxTable):
    zone_name = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)
    status = columns.ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.ProxmoxSdnZone
        fields = (
            "pk",
            "id",
            "zone_name",
            "cluster_name",
            "endpoint",
            "zone_type",
            "controller",
            "vrf_vxlan",
            "status",
            "tags",
            "created",
            "last_updated",
        )
        default_columns = (
            "zone_name",
            "cluster_name",
            "endpoint",
            "zone_type",
            "controller",
            "vrf_vxlan",
            "status",
        )


class ProxmoxSdnVNetTable(NetBoxTable):
    vnet_name = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)
    l2vpn = tables.Column(linkify=True)
    status = columns.ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.ProxmoxSdnVNet
        fields = (
            "pk",
            "id",
            "vnet_name",
            "zone_name",
            "cluster_name",
            "endpoint",
            "vnet_type",
            "tag",
            "l2vpn",
            "status",
            "tags",
            "created",
            "last_updated",
        )
        default_columns = (
            "vnet_name",
            "zone_name",
            "cluster_name",
            "endpoint",
            "vnet_type",
            "tag",
            "l2vpn",
            "status",
        )


class ProxmoxSdnSubnetTable(NetBoxTable):
    subnet = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)
    prefix = tables.Column(linkify=True)
    status = columns.ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.ProxmoxSdnSubnet
        fields = (
            "pk",
            "id",
            "subnet",
            "vnet_name",
            "zone_name",
            "cluster_name",
            "endpoint",
            "prefix",
            "status",
            "tags",
            "created",
            "last_updated",
        )
        default_columns = (
            "subnet",
            "vnet_name",
            "zone_name",
            "cluster_name",
            "endpoint",
            "prefix",
            "status",
        )


class ProxmoxSdnBindingTable(NetBoxTable):
    source_name = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = models.ProxmoxSdnBinding
        fields = (
            "pk",
            "id",
            "source_type",
            "source_name",
            "cluster_name",
            "endpoint",
            "target_type",
            "target_id",
            "status",
            "tags",
            "created",
            "last_updated",
        )
        default_columns = (
            "source_type",
            "source_name",
            "cluster_name",
            "endpoint",
            "target_type",
            "target_id",
            "status",
        )


class ProxmoxSdnRouteMapTable(NetBoxTable):
    name = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)
    status = columns.ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.ProxmoxSdnRouteMap
        fields = (
            "pk",
            "id",
            "name",
            "cluster_name",
            "endpoint",
            "action",
            "order",
            "status",
            "tags",
            "created",
            "last_updated",
        )
        default_columns = (
            "name",
            "cluster_name",
            "endpoint",
            "action",
            "order",
            "status",
        )


class ProxmoxSdnPrefixListTable(NetBoxTable):
    name = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)
    status = columns.ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.ProxmoxSdnPrefixList
        fields = (
            "pk",
            "id",
            "name",
            "cluster_name",
            "endpoint",
            "cidr",
            "action",
            "status",
            "tags",
            "created",
            "last_updated",
        )
        default_columns = (
            "name",
            "cluster_name",
            "endpoint",
            "cidr",
            "action",
            "status",
        )
