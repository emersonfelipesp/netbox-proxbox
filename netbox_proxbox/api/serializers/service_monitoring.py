"""API serializers for Proxmox endpoint service monitoring records."""

from __future__ import annotations

from netbox.api.serializers import NetBoxModelSerializer, WritableNestedSerializer
from rest_framework import serializers

from netbox_proxbox.api.serializers.cluster import NestedProxmoxEndpointSerializer
from netbox_proxbox.models import (
    ProxmoxServiceCollection,
    ProxmoxServiceSample,
    ProxmoxServiceStatus,
)


class NestedProxmoxServiceCollectionSerializer(WritableNestedSerializer):
    """Minimal service collection shape for nested sample rows."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxservicecollection-detail",
    )

    class Meta:
        model = ProxmoxServiceCollection
        fields = ["id", "url", "display", "collected_at", "status"]
        brief_fields = ("id", "url", "display", "collected_at", "status")


class ProxmoxServiceCollectionSerializer(NetBoxModelSerializer):
    """Read representation of one service-monitoring collection run."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxservicecollection-detail",
    )
    endpoint = NestedProxmoxEndpointSerializer()

    class Meta:
        model = ProxmoxServiceCollection
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "collected_at",
            "reachable",
            "trigger",
            "duration_ms",
            "error_message",
            "rpc_execution_id",
            "status",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "endpoint", "status")


class ProxmoxServiceSampleSerializer(NetBoxModelSerializer):
    """Read representation of a raw service row from one collection."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxservicesample-detail",
    )
    collection = NestedProxmoxServiceCollectionSerializer()

    class Meta:
        model = ProxmoxServiceSample
        fields = (
            "id",
            "url",
            "display",
            "collection",
            "unit",
            "service_id",
            "load_state",
            "active_state",
            "sub_state",
            "result",
            "main_pid",
            "exec_main_code",
            "exec_main_status",
            "n_restarts",
            "active_enter_timestamp",
            "unit_file_state",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "collection", "unit", "active_state")


class ProxmoxServiceStatusSerializer(NetBoxModelSerializer):
    """Read representation of the latest projected service state."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxservicestatus-detail",
    )
    endpoint = NestedProxmoxEndpointSerializer()

    class Meta:
        model = ProxmoxServiceStatus
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "unit",
            "service_id",
            "load_state",
            "active_state",
            "sub_state",
            "result",
            "main_pid",
            "exec_main_code",
            "exec_main_status",
            "n_restarts",
            "active_enter_timestamp",
            "unit_file_state",
            "last_seen_at",
            "is_healthy",
            "expected_active",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "endpoint", "unit", "is_healthy")
