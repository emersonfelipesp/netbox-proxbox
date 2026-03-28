"""Serialize ProxBox plugin models for the NetBox plugin API."""

from rest_framework import serializers

from ipam.api.serializers_.nested import NestedIPAddressSerializer
from netbox.api.fields import ChoiceField
from netbox.api.serializers import NetBoxModelSerializer, WritableNestedSerializer
from users.models import Token
from virtualization.api.serializers_.nested import NestedVirtualMachineSerializer

from netbox_proxbox.choices import (
    NetBoxTokenVersionChoices,
    ProxmoxBackupFormatChoices,
    ProxmoxBackupSubtypeChoices,
    ProxmoxModeChoices,
    SyncStatusChoices,
    SyncTypeChoices,
)
from netbox_proxbox.models import (
    FastAPIEndpoint,
    NetBoxEndpoint,
    ProxmoxEndpoint,
    SyncProcess,
    VMBackup,
)


class NestedTokenSerializer(WritableNestedSerializer):
    class Meta:
        model = Token
        fields = ["id", "url", "display", "key"]
        brief_fields = ("id", "url", "display", "key")


class VMBackupSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:vmbackup-detail",
    )
    virtual_machine = NestedVirtualMachineSerializer()
    subtype = ChoiceField(choices=ProxmoxBackupSubtypeChoices)
    format = ChoiceField(choices=ProxmoxBackupFormatChoices)

    class Meta:
        model = VMBackup
        fields = (
            "id",
            "url",
            "display",
            "virtual_machine",
            "storage",
            "subtype",
            "format",
            "creation_time",
            "size",
            "notes",
            "volume_id",
            "vmid",
            "used",
            "encrypted",
            "verification_state",
            "verification_upid",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "storage", "creation_time")


class SyncProcessSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:syncprocess-detail",
    )
    sync_type = ChoiceField(choices=SyncTypeChoices)
    status = ChoiceField(choices=SyncStatusChoices)
    runtime = serializers.FloatField(required=False, allow_null=True)
    started_at = serializers.DateTimeField(required=False, allow_null=True)
    completed_at = serializers.DateTimeField(required=False, allow_null=True)

    class Meta:
        model = SyncProcess
        fields = (
            "id",
            "url",
            "display",
            "name",
            "sync_type",
            "status",
            "started_at",
            "completed_at",
            "runtime",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "status")


class ProxmoxEndpointSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:endpoints:proxmox-endpoint-detail",
    )
    ip_address = NestedIPAddressSerializer(required=False, allow_null=True)
    domain = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    mode = ChoiceField(choices=ProxmoxModeChoices)

    class Meta:
        model = ProxmoxEndpoint
        fields = (
            "id",
            "url",
            "display",
            "name",
            "ip_address",
            "domain",
            "port",
            "mode",
            "version",
            "repoid",
            "username",
            "password",
            "token_name",
            "token_value",
            "verify_ssl",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "domain", "port")
        extra_kwargs = {
            "password": {"write_only": True, "required": False, "allow_null": True},
            "token_value": {"write_only": True, "required": False, "allow_blank": True},
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        domain = (
            attrs.get("domain", getattr(self.instance, "domain", "")) or ""
        ).strip()
        ip_address = attrs.get("ip_address", getattr(self.instance, "ip_address", None))

        if not domain and ip_address is None:
            raise serializers.ValidationError(
                {
                    "domain": "Provide either a domain or an IP address.",
                    "ip_address": "Provide either a domain or an IP address.",
                }
            )

        return attrs


class NetBoxEndpointSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:endpoints:netbox-endpoint-detail",
    )
    ip_address = NestedIPAddressSerializer(required=False, allow_null=True)
    token = NestedTokenSerializer(required=False, allow_null=True)

    class Meta:
        model = NetBoxEndpoint
        fields = (
            "id",
            "url",
            "display",
            "name",
            "ip_address",
            "domain",
            "port",
            "token_version",
            "token",
            "token_key",
            "token_secret",
            "verify_ssl",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "domain", "port")
        extra_kwargs = {
            "token_secret": {
                "write_only": True,
                "required": False,
                "allow_blank": True,
            },
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)

        domain = (
            attrs.get("domain", getattr(self.instance, "domain", "")) or ""
        ).strip()
        ip_address = attrs.get("ip_address", getattr(self.instance, "ip_address", None))
        if not domain and ip_address is None:
            raise serializers.ValidationError(
                {
                    "domain": "Provide either a domain or an IP address.",
                    "ip_address": "Provide either a domain or an IP address.",
                }
            )

        token = attrs.get("token", getattr(self.instance, "token", None))
        token_version = attrs.get(
            "token_version",
            getattr(self.instance, "token_version", NetBoxTokenVersionChoices.V1),
        )
        token_key = (
            attrs.get("token_key", getattr(self.instance, "token_key", "")) or ""
        ).strip()
        token_secret = (
            attrs.get("token_secret", getattr(self.instance, "token_secret", "")) or ""
        ).strip()

        if token is not None:
            selected_token_version = (
                NetBoxTokenVersionChoices.V2
                if getattr(token, "version", None) == 2
                else NetBoxTokenVersionChoices.V1
            )
            if selected_token_version == NetBoxTokenVersionChoices.V2:
                raise serializers.ValidationError(
                    {
                        "token": (
                            "Selected NetBox v2 token cannot be used by this endpoint "
                            "because its secret is not retrievable. Provide token_key and "
                            "token_secret fields instead."
                        )
                    }
                )

            token_plaintext = (getattr(token, "plaintext", "") or "").strip()
            if not token_plaintext:
                raise serializers.ValidationError(
                    {
                        "token": (
                            "Selected NetBox v1 token does not expose a usable plaintext "
                            "value. Create a new v1 token (or use v2 key/secret fields) "
                            "and reselect it."
                        )
                    }
                )

            attrs["token_version"] = selected_token_version
            attrs["token_key"] = ""
            attrs["token_secret"] = ""
        elif token_version == NetBoxTokenVersionChoices.V2:
            if not token_key:
                raise serializers.ValidationError(
                    {"token_key": "Token key is required when using a v2 token."}
                )
            if not token_secret:
                raise serializers.ValidationError(
                    {"token_secret": "Token secret is required when using a v2 token."}
                )
            attrs["token_key"] = token_key
            attrs["token_secret"] = token_secret
        else:
            raise serializers.ValidationError(
                {"token": "Select an existing API token to use v1 authentication."}
            )
            attrs["token_key"] = ""
            attrs["token_secret"] = ""

        return attrs


class FastAPIEndpointSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:endpoints:fastapi-endpoint-detail",
    )
    ip_address = NestedIPAddressSerializer(required=False, allow_null=True)

    class Meta:
        model = FastAPIEndpoint
        fields = (
            "id",
            "url",
            "display",
            "name",
            "ip_address",
            "domain",
            "port",
            "verify_ssl",
            "token",
            "use_websocket",
            "websocket_domain",
            "websocket_port",
            "server_side_websocket",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "domain", "port")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        domain = (
            attrs.get("domain", getattr(self.instance, "domain", "")) or ""
        ).strip()
        ip_address = attrs.get("ip_address", getattr(self.instance, "ip_address", None))

        if not domain and ip_address is None:
            raise serializers.ValidationError(
                {
                    "domain": "Provide either a domain or an IP address.",
                    "ip_address": "Provide either a domain or an IP address.",
                }
            )

        return attrs
