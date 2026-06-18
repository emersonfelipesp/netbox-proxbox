"""API serializers for PBS endpoint, PDM endpoint, and PDM remote models."""

from __future__ import annotations

from netbox.api.serializers import NetBoxModelSerializer, WritableNestedSerializer
from dcim.api.serializers_.sites import SiteSerializer
from ipam.api.serializers_.nested import NestedIPAddressSerializer
from tenancy.api.serializers_.tenants import TenantSerializer
from rest_framework import serializers

from netbox_proxbox.models import PBSEndpoint, PDMEndpoint, PDMRemote


class NestedPBSEndpointSerializer(WritableNestedSerializer):
    """Minimal PBSEndpoint for nested references (e.g. from PDMEndpoint)."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:endpoints:pbsendpoint-detail",
    )

    class Meta:
        model = PBSEndpoint
        fields = ("id", "url", "display", "name")
        brief_fields = ("id", "url", "display", "name")


class NestedPDMEndpointSerializer(WritableNestedSerializer):
    """Minimal PDMEndpoint for nested references."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:endpoints:pdmendpoint-detail",
    )

    class Meta:
        model = PDMEndpoint
        fields = ("id", "url", "display", "name")
        brief_fields = ("id", "url", "display", "name")


class PBSEndpointSerializer(NetBoxModelSerializer):
    """Proxmox Backup Server endpoint with credentials as write-only fields."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:endpoints:pbsendpoint-detail",
    )
    ip_address = NestedIPAddressSerializer(required=False, allow_null=True)
    site = SiteSerializer(nested=True, required=False, allow_null=True)
    tenant = TenantSerializer(nested=True, required=False, allow_null=True)

    class Meta:
        model = PBSEndpoint
        fields = (
            "id",
            "url",
            "display",
            "name",
            "ip_address",
            "domain",
            "port",
            "token_id",
            "token_secret",
            "fingerprint",
            "verify_ssl",
            "allow_writes",
            "enabled",
            "timeout",
            "site",
            "tenant",
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

    def validate(self, attrs: dict) -> dict:
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


class PDMEndpointSerializer(NetBoxModelSerializer):
    """Proxmox Datacenter Manager endpoint with federation M2M links."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:endpoints:pdmendpoint-detail",
    )
    ip_address = NestedIPAddressSerializer(required=False, allow_null=True)
    site = SiteSerializer(nested=True, required=False, allow_null=True)
    tenant = TenantSerializer(nested=True, required=False, allow_null=True)
    proxmox_endpoints = serializers.SerializerMethodField()
    pbs_endpoints = serializers.SerializerMethodField()

    class Meta:
        model = PDMEndpoint
        fields = (
            "id",
            "url",
            "display",
            "name",
            "ip_address",
            "domain",
            "port",
            "token_id",
            "token_secret",
            "fingerprint",
            "verify_ssl",
            "allow_writes",
            "enabled",
            "timeout",
            "proxmox_endpoints",
            "pbs_endpoints",
            "site",
            "tenant",
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

    def get_proxmox_endpoints(self, obj: PDMEndpoint) -> list:
        from netbox_proxbox.api.serializers.cluster import (
            NestedProxmoxEndpointSerializer,
        )

        return NestedProxmoxEndpointSerializer(
            obj.proxmox_endpoints.all(), many=True, context=self.context
        ).data

    def get_pbs_endpoints(self, obj: PDMEndpoint) -> list:
        return NestedPBSEndpointSerializer(
            obj.pbs_endpoints.all(), many=True, context=self.context
        ).data

    def validate(self, attrs: dict) -> dict:
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


class PDMRemoteSerializer(NetBoxModelSerializer):
    """Discovered PDM remote: one row of PDM's /pdm/remotes reflected in NetBox."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:pdmremote-detail",
    )
    pdm_endpoint = NestedPDMEndpointSerializer()

    class Meta:
        model = PDMRemote
        fields = (
            "id",
            "url",
            "display",
            "pdm_endpoint",
            "name",
            "type",
            "hostname",
            "fingerprint",
            "version",
            "linked_proxmox_endpoint",
            "linked_pbs_endpoint",
            "last_seen_at",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "type", "pdm_endpoint")
