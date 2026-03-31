"""API serializer for Proxmox storage records."""

from __future__ import annotations

from netbox.api.serializers import NetBoxModelSerializer, WritableNestedSerializer
from rest_framework import serializers

from netbox_proxbox.models import ProxmoxStorage


class ProxmoxStorageSerializer(NetBoxModelSerializer):
    """Full representation of synced Proxmox storage rows."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:storage-detail",
    )

    class Meta:
        model = ProxmoxStorage
        fields = (
            "id",
            "url",
            "display",
            "cluster",
            "name",
            "storage_type",
            "content",
            "path",
            "nodes",
            "shared",
            "enabled",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "cluster", "name")


class NestedProxmoxStorageSerializer(WritableNestedSerializer):
    """Minimal nested representation for Proxmox storage relations."""

    class Meta:
        model = ProxmoxStorage
        fields = ("id", "url", "display", "cluster", "name")
        brief_fields = ("id", "url", "display", "cluster", "name")
