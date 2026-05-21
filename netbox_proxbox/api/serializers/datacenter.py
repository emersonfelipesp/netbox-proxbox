"""API serializers for Proxmox datacenter models."""

from __future__ import annotations

from netbox.api.fields import ChoiceField
from netbox.api.serializers import NetBoxModelSerializer

from netbox_proxbox.choices import FirewallSyncStatusChoices
from netbox_proxbox.models import ProxmoxDatacenterCpuModel


class ProxmoxDatacenterCpuModelSerializer(NetBoxModelSerializer):
    status = ChoiceField(choices=FirewallSyncStatusChoices, required=False)

    class Meta:
        model = ProxmoxDatacenterCpuModel
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "cluster_name",
            "cputype",
            "base_cputype",
            "flags",
            "vendor_id",
            "level",
            "description",
            "status",
            "raw_config",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
