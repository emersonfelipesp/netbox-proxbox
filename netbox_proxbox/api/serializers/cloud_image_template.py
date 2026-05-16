"""API serializer for tenant-scoped cloud image templates."""

from __future__ import annotations

from netbox.api.fields import ChoiceField
from netbox.api.serializers import NetBoxModelSerializer, WritableNestedSerializer
from rest_framework import serializers
from tenancy.api.serializers_.tenants import TenantSerializer
from virtualization.api.serializers_.clusters import ClusterSerializer

from netbox_proxbox.choices import CloudImageOSFamilyChoices
from netbox_proxbox.models import CloudImageTemplate


class CloudImageTemplateSerializer(NetBoxModelSerializer):
    """Full representation of a Cloud Portal cloud image template."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:cloudimagetemplate-detail",
    )
    cluster = ClusterSerializer(nested=True)
    os_family = ChoiceField(choices=CloudImageOSFamilyChoices)
    allowed_tenants = TenantSerializer(nested=True, many=True, required=False)

    class Meta:
        model = CloudImageTemplate
        fields = (
            "id",
            "url",
            "display",
            "name",
            "slug",
            "description",
            "cluster",
            "source_vmid",
            "os_family",
            "os_release",
            "default_ciuser",
            "allowed_tenants",
            "is_active",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = (
            "id",
            "url",
            "display",
            "name",
            "slug",
            "cluster",
            "source_vmid",
            "os_family",
            "os_release",
            "default_ciuser",
            "is_active",
        )

    def _apply_allowed_tenants(self, instance, allowed_tenants):
        if allowed_tenants is not None:
            instance.allowed_tenants.set(allowed_tenants)

    def create(self, validated_data):
        """Create while applying tenant scope after the instance exists."""
        allowed_tenants = validated_data.pop("allowed_tenants", None)
        instance = super().create(validated_data)
        self._apply_allowed_tenants(instance, allowed_tenants)
        return instance

    def update(self, instance, validated_data):
        """Update writable nested fields without DRF's default nested assertion."""
        allowed_tenants = validated_data.pop("allowed_tenants", None)
        instance = super().update(instance, validated_data)
        self._apply_allowed_tenants(instance, allowed_tenants)
        return instance


class NestedCloudImageTemplateSerializer(WritableNestedSerializer):
    """Nested cloud image template representation for related serializers."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:cloudimagetemplate-detail",
    )

    class Meta:
        model = CloudImageTemplate
        fields = (
            "id",
            "url",
            "display",
            "name",
            "slug",
            "source_vmid",
        )
        brief_fields = ("id", "url", "display", "name", "slug")
