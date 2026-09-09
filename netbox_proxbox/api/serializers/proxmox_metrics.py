"""API serializer for plugin-owned Proxmox InfluxDB metrics."""

from __future__ import annotations

from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from netbox_proxbox.models import ProxmoxMetricsInfluxDB, ProxboxPluginSettings
from netbox_proxbox.utils import encryption as enc_helpers
from netbox_proxbox.utils.metrics import (
    validate_metrics_interval,
    validate_metrics_time,
)
from netbox_proxbox.api.serializers.cluster import (
    NestedProxmoxClusterSerializer,
    NestedProxmoxEndpointSerializer,
)


class ProxmoxMetricsInfluxDBSerializer(NetBoxModelSerializer):
    """CRUD serializer with a write-only query token input."""

    endpoint = NestedProxmoxEndpointSerializer()
    proxmox_cluster = NestedProxmoxClusterSerializer()
    query_token = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )
    query_token_configured = serializers.BooleanField(
        source="has_query_token", read_only=True
    )
    credential_encryption_state = serializers.CharField(read_only=True)

    def _resolve_encryption_key(self) -> str:
        key = ProxboxPluginSettings.get_solo().encryption_key or ""
        if not key:
            raise serializers.ValidationError(
                {
                    "detail": "Configure the Proxbox encryption key before storing metrics tokens."
                }
            )
        return key

    def _apply_tokens(
        self, instance: ProxmoxMetricsInfluxDB, validated_data: dict
    ) -> None:
        query_token = validated_data.pop("query_token", None)
        if not query_token:
            return
        key = self._resolve_encryption_key()
        try:
            if query_token:
                instance.set_query_token(query_token, key=key)
        except enc_helpers.EncryptionError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

    def create(self, validated_data: dict) -> ProxmoxMetricsInfluxDB:
        tags = validated_data.pop("tags", None)
        token_data = {"query_token": validated_data.pop("query_token", None)}
        instance = ProxmoxMetricsInfluxDB(**validated_data)
        self._apply_tokens(instance, token_data)
        instance.full_clean()
        instance.save()
        if tags is not None:
            instance.tags.set(tags)
        return instance

    def update(
        self, instance: ProxmoxMetricsInfluxDB, validated_data: dict
    ) -> ProxmoxMetricsInfluxDB:
        tags = validated_data.pop("tags", None)
        self._apply_tokens(instance, validated_data)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.full_clean()
        instance.save()
        if tags is not None:
            instance.tags.set(tags)
        return instance

    def to_representation(self, instance: ProxmoxMetricsInfluxDB):
        """Return state booleans, never ciphertext or plaintext tokens."""
        representation = super().to_representation(instance)
        representation["influx_url"] = instance.influx_url_display
        representation["query_token_configured"] = instance.has_query_token
        representation["credential_encryption_state"] = (
            instance.credential_encryption_state
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
            "query_token",
            "query_token_configured",
            "credential_encryption_state",
            "verify_tls",
            "enabled",
            "comments",
            "created",
            "last_updated",
            "custom_fields",
            "tags",
        )
        read_only_fields = (
            "id",
            "url",
            "display",
            "query_token_configured",
            "credential_encryption_state",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "enabled")


class ProxmoxMetricsInfluxDBQuerySerializer(serializers.Serializer):
    """Bounded query filters; arbitrary Flux is intentionally not accepted."""

    time_start = serializers.CharField(required=False, default="-1h", max_length=64)
    time_stop = serializers.CharField(required=False, default="now()", max_length=64)
    measurement = serializers.CharField(max_length=128)
    field = serializers.CharField(required=False, allow_blank=True, max_length=128)
    node = serializers.CharField(required=False, allow_blank=True, max_length=128)
    vmid = serializers.IntegerField(required=False, min_value=0)
    tag_key = serializers.CharField(required=False, allow_blank=True, max_length=64)
    tag_value = serializers.CharField(required=False, allow_blank=True, max_length=256)
    aggregation_every = serializers.CharField(
        required=False, allow_blank=True, max_length=32
    )
    aggregation_function = serializers.ChoiceField(
        required=False,
        choices=("count", "first", "last", "max", "mean", "min", "sum"),
    )
    limit = serializers.IntegerField(
        required=False, default=500, min_value=1, max_value=5000
    )

    def validate_time_start(self, value: str) -> str:
        return validate_metrics_time(value)

    def validate_time_stop(self, value: str) -> str:
        return validate_metrics_time(value, allow_now=True)

    def validate_aggregation_every(self, value: str) -> str:
        return validate_metrics_interval(value)
