"""API serializers for ProxmoxCluster and ProxmoxNode models."""

from __future__ import annotations

from netbox.api.fields import ChoiceField
from netbox.api.serializers import NetBoxModelSerializer, WritableNestedSerializer
from rest_framework import serializers
from virtualization.api.serializers_.clusters import ClusterSerializer
from dcim.choices import DeviceStatusChoices
from dcim.models import Device

from netbox_proxbox.choices import ProxmoxModeChoices
from netbox_proxbox.models import ProxmoxCluster, ProxmoxNode
from netbox_proxbox.api.serializers.endpoints import ProxmoxEndpointSerializer


class NestedDeviceWithStatusSerializer(WritableNestedSerializer):
    """Minimal Device serializer that also exposes the NetBox device status."""

    status = ChoiceField(choices=DeviceStatusChoices)

    class Meta:
        model = Device
        fields = ["id", "url", "display", "name", "status"]
        brief_fields = ("id", "url", "display", "name")


class NestedProxmoxEndpointSerializer(WritableNestedSerializer):
    """Minimal ProxmoxEndpoint for nested references."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:endpoints:proxmoxendpoint-detail",
    )

    class Meta:
        from netbox_proxbox.models import ProxmoxEndpoint

        model = ProxmoxEndpoint
        fields = ["id", "url", "display", "name"]
        brief_fields = ("id", "url", "display", "name")


class NestedProxmoxClusterSerializer(WritableNestedSerializer):
    """Minimal ProxmoxCluster for nested references."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxcluster-detail",
    )

    class Meta:
        model = ProxmoxCluster
        fields = ["id", "url", "display", "name"]
        brief_fields = ("id", "url", "display", "name")


class NestedProxmoxNodeSerializer(WritableNestedSerializer):
    """Minimal ProxmoxNode for nested references."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxnode-detail",
    )

    class Meta:
        model = ProxmoxNode
        fields = ["id", "url", "display", "name", "node_id", "online"]
        brief_fields = ("id", "url", "display", "name", "node_id", "online")


class ProxmoxClusterSerializer(NetBoxModelSerializer):
    """Full ProxmoxCluster serializer with nested relationships."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxcluster-detail",
    )
    endpoint = NestedProxmoxEndpointSerializer()
    netbox_cluster = ClusterSerializer(nested=True, required=False, allow_null=True)
    mode = ChoiceField(choices=ProxmoxModeChoices)
    node_count = serializers.IntegerField(source="nodes_count", read_only=True)

    class Meta:
        model = ProxmoxCluster
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "netbox_cluster",
            "name",
            "cluster_id",
            "mode",
            "nodes_count",
            "node_count",
            "quorate",
            "version",
            "created",
            "last_updated",
            "custom_fields",
            "tags",
        )
        brief_fields = ("id", "url", "display", "name")


class ProxmoxNodeSerializer(NetBoxModelSerializer):
    """Full ProxmoxNode serializer with nested relationships."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxnode-detail",
    )
    endpoint = NestedProxmoxEndpointSerializer()
    proxmox_cluster = NestedProxmoxClusterSerializer(required=False, allow_null=True)
    netbox_device = NestedDeviceWithStatusSerializer(required=False, allow_null=True)
    memory_usage_percent = serializers.FloatField(read_only=True)
    cpu_usage_percent = serializers.FloatField(read_only=True)

    class Meta:
        model = ProxmoxNode
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "proxmox_cluster",
            "netbox_device",
            "name",
            "node_id",
            "ip_address",
            "online",
            "local",
            "cpu_usage",
            "cpu_usage_percent",
            "max_cpu",
            "memory_usage",
            "memory_usage_percent",
            "max_memory",
            "ssl_fingerprint",
            "support_level",
            "default_role_qemu",
            "default_role_lxc",
            "created",
            "last_updated",
            "custom_fields",
            "tags",
        )
        brief_fields = ("id", "url", "display", "name", "online")
