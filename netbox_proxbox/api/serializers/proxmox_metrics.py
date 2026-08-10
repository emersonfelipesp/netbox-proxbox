"""API serializers for Proxmox metrics integrations."""

from __future__ import annotations

from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from netbox_proxbox.api.serializers.cluster import (
    NestedProxmoxClusterSerializer,
    NestedProxmoxEndpointSerializer,
)
from netbox_proxbox.models import ProxmoxMetricsInfluxDB


class ProxmoxMetricsInfluxDBSerializer(NetBoxModelSerializer):
    """InfluxDB metadata for querying Proxmox cluster metrics."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxmetricsinfluxdb-detail",
    )
    endpoint = NestedProxmoxEndpointSerializer()
    proxmox_cluster = NestedProxmoxClusterSerializer()

    def to_representation(self, instance: ProxmoxMetricsInfluxDB):
        """Mask non-conforming stored URLs and secret references on output."""
        representation = super().to_representation(instance)
        representation["influx_url"] = instance.influx_url_display
        representation["query_token_secret_ref"] = (
            instance.query_token_secret_ref_display
        )
        representation["writer_token_secret_ref"] = (
            instance.writer_token_secret_ref_display
        )
        return representation

    class Meta:
        model = ProxmoxMetricsInfluxDB
        fields = (
            "id",
            "url",
            "display",
            "name",
            "endpoint",
            "proxmox_cluster",
            "influx_url",
            "org",
            "bucket",
            "measurement_prefix",
            "query_token_secret_ref",
            "writer_token_secret_ref",
            "verify_tls",
            "enabled",
            "comments",
            "created",
            "last_updated",
            "custom_fields",
            "tags",
        )
        brief_fields = ("id", "url", "display", "name", "enabled")
