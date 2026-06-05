"""API serializers for Proxmox, NetBox, and FastAPI endpoint plugin models."""

from __future__ import annotations

from django.utils.translation import gettext as _

from netbox.api.fields import ChoiceField
from netbox.api.serializers import NetBoxModelSerializer, WritableNestedSerializer
from dcim.api.serializers_.sites import SiteSerializer
from ipam.api.serializers_.nested import NestedIPAddressSerializer
from tenancy.api.serializers_.tenants import TenantSerializer
from rest_framework import serializers
from users.models import Token

from netbox_proxbox.choices import (
    NetBoxTokenVersionChoices,
    ProxmoxEndpointEnvironmentChoices,
    ProxmoxModeChoices,
)
from netbox_proxbox.constants import OVERWRITE_FIELDS, SYNC_MODE_FIELDS
from netbox_proxbox.models import FastAPIEndpoint, NetBoxEndpoint, ProxmoxEndpoint


class NestedTokenSerializer(WritableNestedSerializer):
    """Minimal token shape for nested NetBox endpoint writes."""

    class Meta:
        model = Token
        fields = ["id", "url", "display", "key"]
        brief_fields = ("id", "url", "display", "key")


class ProxmoxEndpointSerializer(NetBoxModelSerializer):
    """Proxmox endpoint including secrets as write-only fields."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:endpoints:proxmoxendpoint-detail",
    )
    ip_address = NestedIPAddressSerializer(required=False, allow_null=True)
    domain = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    mode = ChoiceField(choices=ProxmoxModeChoices)
    environment = ChoiceField(
        choices=ProxmoxEndpointEnvironmentChoices,
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    site = SiteSerializer(nested=True, required=False, allow_null=True)
    tenant = TenantSerializer(nested=True, required=False, allow_null=True)
    has_ssh_password = serializers.BooleanField(read_only=True)
    has_ssh_private_key = serializers.BooleanField(read_only=True)
    has_ssh_terminal_credentials = serializers.BooleanField(read_only=True)

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
            "environment",
            "version",
            "repoid",
            "username",
            "password",
            "token_name",
            "token_value",
            "verify_ssl",
            "enabled",
            "timeout",
            "max_retries",
            "retry_backoff",
            "ssh_username",
            "ssh_port",
            "ssh_auth_method",
            "ssh_known_host_fingerprint",
            "has_ssh_password",
            "has_ssh_private_key",
            "has_ssh_terminal_credentials",
            "default_role_qemu",
            "default_role_lxc",
            "enable_tenant_name_regex",
            "tenant_name_regex_rules",
            "enable_tenant_tag_assignment",
            *SYNC_MODE_FIELDS,
            *OVERWRITE_FIELDS,
            "site",
            "tenant",
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

    def get_display(self, obj: ProxmoxEndpoint) -> str:
        """Label for list APIs and APISelect (e.g. schedule sync): ``Name (IP)``."""
        name_part = (obj.name or "").strip() or _("Proxmox endpoint")
        ip_part = obj.ip
        if ip_part:
            return f"{name_part} ({ip_part})"
        domain_part = (obj.domain or "").strip()
        if domain_part:
            return f"{name_part} ({domain_part})"
        return name_part

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        """Require at least one of domain or IP address for reachability."""
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
    """Remote NetBox API endpoint with v1 token or v2 key/secret validation."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:endpoints:netboxendpoint-detail",
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
            "enabled",
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

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        """Enforce host target plus consistent v1 token vs v2 key/secret auth rules."""
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
            attrs["token_version"] = NetBoxTokenVersionChoices.V1
            attrs["token_key"] = ""
            attrs["token_secret"] = ""

        return attrs


class FastAPIEndpointSerializer(NetBoxModelSerializer):
    """ProxBox backend HTTP/WebSocket endpoint."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:endpoints:fastapiendpoint-detail",
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
            "use_https",
            "verify_ssl",
            "enabled",
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

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        """Require at least one of domain or IP address for the backend URL."""
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
