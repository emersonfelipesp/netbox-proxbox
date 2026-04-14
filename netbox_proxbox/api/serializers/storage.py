"""API serializer for Proxmox storage records."""

from __future__ import annotations

from netbox.api.serializers import NetBoxModelSerializer, WritableNestedSerializer
from rest_framework import serializers
from virtualization.api.serializers import ClusterSerializer

from netbox_proxbox.models import ProxmoxStorage


class ProxmoxStorageSerializer(NetBoxModelSerializer):
    """Full representation of synced Proxmox storage rows."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:storage-detail",
    )
    cluster = ClusterSerializer(nested=True)

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
            # Remote-host fields
            "server",
            "port",
            "username",
            # NFS / CIFS
            "export",
            "share",
            # Ceph / RBD
            "pool",
            "monhost",
            "namespace",
            # PBS
            "datastore",
            "subdir",
            # Filesystem
            "mountpoint",
            "is_mountpoint",
            "preallocation",
            "format",
            # Retention / backup
            "prune_backups",
            "max_protected_backups",
            # Full raw config
            "raw_config",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "cluster", "name")

    def create(self, validated_data: dict) -> ProxmoxStorage:
        """Upsert by (cluster, name) so bulk and single POSTs are both idempotent."""
        cluster = validated_data.get("cluster")
        name = validated_data.get("name")
        if cluster is not None and name:
            existing = ProxmoxStorage.objects.filter(cluster=cluster, name=name).first()
            if existing is not None:
                return self.update(existing, validated_data)
        return super().create(validated_data)


class NestedProxmoxStorageSerializer(WritableNestedSerializer):
    """Minimal nested representation for Proxmox storage relations."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:storage-detail",
    )
    cluster = ClusterSerializer(nested=True)

    class Meta:
        model = ProxmoxStorage
        fields = ("id", "url", "display", "cluster", "name")
        brief_fields = ("id", "url", "display", "cluster", "name")
        validators = []
