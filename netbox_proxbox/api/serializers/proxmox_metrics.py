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
