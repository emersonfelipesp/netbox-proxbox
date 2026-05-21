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
        default_columns = ("fabric_name", "cluster_name", "endpoint", "fabric_type", "asn", "status")


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
        default_columns = ("name", "cluster_name", "endpoint", "action", "order", "status")


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
        default_columns = ("name", "cluster_name", "endpoint", "cidr", "action", "status")
