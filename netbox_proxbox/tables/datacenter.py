"""Tables for Proxmox datacenter models."""

from __future__ import annotations

import django_tables2 as tables
from netbox.tables import NetBoxTable, columns

from netbox_proxbox import models


class ProxmoxDatacenterCpuModelTable(NetBoxTable):
    cputype = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)
    status = columns.ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = models.ProxmoxDatacenterCpuModel
        fields = (
            "pk",
            "id",
            "cputype",
            "cluster_name",
            "endpoint",
            "base_cputype",
            "flags",
            "vendor_id",
            "level",
            "status",
            "tags",
            "created",
            "last_updated",
        )
        default_columns = ("cputype", "cluster_name", "endpoint", "base_cputype", "status")
