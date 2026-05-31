"""API serializer for dedicated Proxmox VM template inventory."""

from __future__ import annotations

from netbox.api.serializers import NetBoxModelSerializer, WritableNestedSerializer
from rest_framework import serializers
from virtualization.api.serializers_.nested import NestedVirtualMachineSerializer

from netbox_proxbox.api.serializers.cluster import (
    NestedProxmoxClusterSerializer,
    NestedProxmoxEndpointSerializer,
    NestedProxmoxNodeSerializer,
)
from netbox_proxbox.models import ProxmoxVMTemplate


class NestedProxmoxVMTemplateSerializer(WritableNestedSerializer):
    """Nested Proxmox VM template representation."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxvmtemplate-detail",
    )

    class Meta:
        model = ProxmoxVMTemplate
        fields = ("id", "url", "display", "name", "vmid", "proxmox_type")
        brief_fields = ("id", "url", "display", "name", "vmid")


class ProxmoxVMTemplateSerializer(NetBoxModelSerializer):
    """Full representation of a synced Proxmox VM template row."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxvmtemplate-detail",
    )
    proxmox_endpoint = NestedProxmoxEndpointSerializer()
    cluster = NestedProxmoxClusterSerializer(required=False, allow_null=True)
    node = NestedProxmoxNodeSerializer(required=False, allow_null=True)
    source_vm = NestedVirtualMachineSerializer(required=False, allow_null=True)
    cloned_vms = NestedVirtualMachineSerializer(
        many=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = ProxmoxVMTemplate
        fields = (
            "id",
            "url",
            "display",
            "name",
            "vmid",
            "proxmox_endpoint",
            "cluster",
            "node",
            "source_vm",
            "cloned_vms",
            "node_name",
            "proxmox_type",
            "status",
            "vcpus",
            "memory",
            "disk",
            "os_type",
            "description",
            "cloud_init_enabled",
            "net_config",
            "disk_config",
            "raw_config",
            "last_synced",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = (
            "id",
            "url",
            "display",
            "name",
            "vmid",
            "proxmox_type",
            "status",
        )
