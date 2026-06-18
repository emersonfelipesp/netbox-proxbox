"""API serializers for Firecracker Cloud inventory."""

from __future__ import annotations

from netbox.api.fields import ChoiceField
from netbox.api.serializers import NetBoxModelSerializer, WritableNestedSerializer
from rest_framework import serializers
from tenancy.api.serializers_.tenants import TenantSerializer
from virtualization.api.serializers_.nested import NestedVirtualMachineSerializer

from netbox_proxbox.api.serializers.cluster import NestedProxmoxNodeSerializer
from netbox_proxbox.choices import (
    CloudImageOSFamilyChoices,
    FirecrackerHostStatusChoices,
    FirecrackerMicroVMStatusChoices,
    FirecrackerNetworkModeChoices,
)
from netbox_proxbox.models import (
    FirecrackerHost,
    FirecrackerHostPool,
    FirecrackerImageTemplate,
    FirecrackerMicroVM,
)


class NestedFirecrackerHostPoolSerializer(WritableNestedSerializer):
    """Minimal Firecracker host-pool representation."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:firecrackerhostpool-detail",
    )

    class Meta:
        model = FirecrackerHostPool
        fields = ("id", "url", "display", "name", "slug")
        brief_fields = ("id", "url", "display", "name", "slug")


class NestedFirecrackerHostSerializer(WritableNestedSerializer):
    """Minimal Firecracker host representation."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:firecrackerhost-detail",
    )

    class Meta:
        model = FirecrackerHost
        fields = ("id", "url", "display", "name", "status")
        brief_fields = ("id", "url", "display", "name", "status")


class NestedFirecrackerImageTemplateSerializer(WritableNestedSerializer):
    """Minimal Firecracker image-template representation."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:firecrackerimagetemplate-detail",
    )

    class Meta:
        model = FirecrackerImageTemplate
        fields = ("id", "url", "display", "name", "slug", "architecture")
        brief_fields = ("id", "url", "display", "name", "slug", "architecture")


class FirecrackerHostPoolSerializer(NetBoxModelSerializer):
    """Full representation of a Firecracker host pool."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:firecrackerhostpool-detail",
    )
    default_network_mode = ChoiceField(choices=FirecrackerNetworkModeChoices)
    allowed_tenants = TenantSerializer(nested=True, many=True, required=False)

    class Meta:
        model = FirecrackerHostPool
        fields = (
            "id",
            "url",
            "display",
            "name",
            "slug",
            "description",
            "default_network_mode",
            "allowed_tenants",
            "is_active",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "slug", "is_active")

    def _apply_allowed_tenants(
        self,
        instance: FirecrackerHostPool,
        allowed_tenants: object | None,
    ) -> None:
        if allowed_tenants is None:
            return

        instance.allowed_tenants.set(allowed_tenants)

    def create(self, validated_data: dict[str, object]) -> FirecrackerHostPool:
        allowed_tenants = validated_data.pop("allowed_tenants", None)
        instance = super().create(validated_data)
        self._apply_allowed_tenants(instance, allowed_tenants)
        return instance

    def update(
        self,
        instance: FirecrackerHostPool,
        validated_data: dict[str, object],
    ) -> FirecrackerHostPool:
        allowed_tenants = validated_data.pop("allowed_tenants", None)
        instance = super().update(instance, validated_data)
        self._apply_allowed_tenants(instance, allowed_tenants)
        return instance


class FirecrackerHostSerializer(NetBoxModelSerializer):
    """Full representation of a Firecracker host-agent VM."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:firecrackerhost-detail",
    )
    pool = NestedFirecrackerHostPoolSerializer()
    host_vm = NestedVirtualMachineSerializer(required=False, allow_null=True)
    proxmox_node = NestedProxmoxNodeSerializer(required=False, allow_null=True)
    status = ChoiceField(choices=FirecrackerHostStatusChoices)
    token_configured = serializers.BooleanField(read_only=True)
    available_vcpus = serializers.IntegerField(read_only=True)
    available_memory_mib = serializers.IntegerField(read_only=True)
    available_disk_mib = serializers.IntegerField(read_only=True)

    class Meta:
        model = FirecrackerHost
        fields = (
            "id",
            "url",
            "display",
            "pool",
            "name",
            "host_vm",
            "proxmox_node",
            "agent_base_url",
            "token_configured",
            "status",
            "firecracker_version",
            "kvm_available",
            "supports_nat",
            "supports_bridge",
            "capacity_vcpus",
            "capacity_memory_mib",
            "capacity_disk_mib",
            "allocated_vcpus",
            "allocated_memory_mib",
            "allocated_disk_mib",
            "available_vcpus",
            "available_memory_mib",
            "available_disk_mib",
            "last_seen",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = (
            "id",
            "url",
            "display",
            "pool",
            "name",
            "status",
            "agent_base_url",
        )


class FirecrackerImageTemplateSerializer(NetBoxModelSerializer):
    """Full representation of a Firecracker kernel/rootfs image bundle."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:firecrackerimagetemplate-detail",
    )
    os_family = ChoiceField(choices=CloudImageOSFamilyChoices)
    allowed_tenants = TenantSerializer(nested=True, many=True, required=False)

    class Meta:
        model = FirecrackerImageTemplate
        fields = (
            "id",
            "url",
            "display",
            "name",
            "slug",
            "description",
            "architecture",
            "os_family",
            "os_release",
            "kernel_image_url",
            "kernel_image_sha256",
            "rootfs_image_url",
            "rootfs_image_sha256",
            "default_kernel_args",
            "default_user",
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
            "architecture",
            "os_family",
            "os_release",
            "is_active",
        )

    def _apply_allowed_tenants(
        self,
        instance: FirecrackerImageTemplate,
        allowed_tenants: object | None,
    ) -> None:
        if allowed_tenants is None:
            return

        instance.allowed_tenants.set(allowed_tenants)

    def create(self, validated_data: dict[str, object]) -> FirecrackerImageTemplate:
        allowed_tenants = validated_data.pop("allowed_tenants", None)
        instance = super().create(validated_data)
        self._apply_allowed_tenants(instance, allowed_tenants)
        return instance

    def update(
        self,
        instance: FirecrackerImageTemplate,
        validated_data: dict[str, object],
    ) -> FirecrackerImageTemplate:
        allowed_tenants = validated_data.pop("allowed_tenants", None)
        instance = super().update(instance, validated_data)
        self._apply_allowed_tenants(instance, allowed_tenants)
        return instance


class FirecrackerMicroVMSerializer(NetBoxModelSerializer):
    """Full representation of a provisioned Firecracker micro-VM."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:firecrackermicrovm-detail",
    )
    host = NestedFirecrackerHostSerializer()
    image = NestedFirecrackerImageTemplateSerializer()
    tenant = TenantSerializer(nested=True, required=False, allow_null=True)
    status = ChoiceField(choices=FirecrackerMicroVMStatusChoices)
    network_mode = ChoiceField(choices=FirecrackerNetworkModeChoices)
    instance_ref = serializers.CharField(read_only=True)

    class Meta:
        model = FirecrackerMicroVM
        fields = (
            "id",
            "url",
            "display",
            "instance_ref",
            "microvm_id",
            "name",
            "tenant",
            "host",
            "image",
            "status",
            "network_mode",
            "vcpus",
            "memory_mib",
            "disk_mib",
            "guest_ip",
            "mac_address",
            "bridge_name",
            "tap_name",
            "ssh_authorized_keys",
            "agent_payload",
            "last_agent_state",
            "started_at",
            "stopped_at",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = (
            "id",
            "url",
            "display",
            "instance_ref",
            "name",
            "status",
            "tenant",
        )
