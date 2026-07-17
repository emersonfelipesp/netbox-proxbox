"""API serializers for typed Proxbox sync-state sidecar models."""

from __future__ import annotations

from dcim.models import Device, DeviceRole, DeviceType, Interface, Manufacturer, Site
from ipam.models import IPAddress, VLAN
from netbox.api.serializers import NetBoxModelSerializer, WritableNestedSerializer
from rest_framework import serializers
from utilities.api import get_related_object_by_attrs
from virtualization.models import (
    Cluster,
    ClusterGroup,
    ClusterType,
    VirtualDisk,
    VirtualMachine,
    VMInterface,
)

from netbox_proxbox.api.serializers.cluster import (
    NestedProxmoxClusterSerializer,
    NestedProxmoxEndpointSerializer,
    NestedProxmoxNodeSerializer,
)
from netbox_proxbox.models import (
    ProxboxClusterGroupSyncState,
    ProxboxClusterSyncState,
    ProxboxClusterTypeSyncState,
    ProxboxDeviceRoleSyncState,
    ProxboxDeviceSyncState,
    ProxboxDeviceTypeSyncState,
    ProxboxIPAddressSyncState,
    ProxboxInterfaceSyncState,
    ProxboxManufacturerSyncState,
    ProxboxSiteSyncState,
    ProxboxVirtualDiskSyncState,
    ProxboxVirtualMachineSyncState,
    ProxboxVLANSyncState,
    ProxboxVMInterfaceSyncState,
)


class RestrictedNestedObjectMixin:
    """Resolve writable nested objects through the caller's view permissions."""

    def to_internal_value(self, data):
        queryset = self.Meta.model.objects.all()
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is not None and hasattr(queryset, "restrict"):
            queryset = queryset.restrict(user, "view")
        return get_related_object_by_attrs(queryset, data)


class RestrictedNestedProxmoxEndpointSerializer(
    RestrictedNestedObjectMixin,
    NestedProxmoxEndpointSerializer,
):
    pass


class RestrictedNestedProxmoxNodeSerializer(
    RestrictedNestedObjectMixin,
    NestedProxmoxNodeSerializer,
):
    pass


class RestrictedNestedProxmoxClusterSerializer(
    RestrictedNestedObjectMixin,
    NestedProxmoxClusterSerializer,
):
    pass


class NestedVirtualMachineSerializer(
    RestrictedNestedObjectMixin,
    WritableNestedSerializer,
):
    class Meta:
        model = VirtualMachine
        fields = ("id", "url", "display", "name")
        brief_fields = ("id", "url", "display", "name")


class NestedDeviceSerializer(RestrictedNestedObjectMixin, WritableNestedSerializer):
    class Meta:
        model = Device
        fields = ("id", "url", "display", "name")
        brief_fields = ("id", "url", "display", "name")


class NestedClusterSerializer(RestrictedNestedObjectMixin, WritableNestedSerializer):
    class Meta:
        model = Cluster
        fields = ("id", "url", "display", "name")
        brief_fields = ("id", "url", "display", "name")


class NestedIPAddressSerializer(RestrictedNestedObjectMixin, WritableNestedSerializer):
    class Meta:
        model = IPAddress
        fields = ("id", "url", "display", "address")
        brief_fields = ("id", "url", "display", "address")


class NestedInterfaceSerializer(RestrictedNestedObjectMixin, WritableNestedSerializer):
    class Meta:
        model = Interface
        fields = ("id", "url", "display", "name")
        brief_fields = ("id", "url", "display", "name")


class NestedVLANSerializer(RestrictedNestedObjectMixin, WritableNestedSerializer):
    class Meta:
        model = VLAN
        fields = ("id", "url", "display", "vid", "name")
        brief_fields = ("id", "url", "display", "vid", "name")


class NestedClusterGroupSerializer(
    RestrictedNestedObjectMixin,
    WritableNestedSerializer,
):
    class Meta:
        model = ClusterGroup
        fields = ("id", "url", "display", "name")
        brief_fields = ("id", "url", "display", "name")


class NestedVirtualDiskSerializer(
    RestrictedNestedObjectMixin,
    WritableNestedSerializer,
):
    class Meta:
        model = VirtualDisk
        fields = ("id", "url", "display", "name")
        brief_fields = ("id", "url", "display", "name")


class NestedVMInterfaceSerializer(
    RestrictedNestedObjectMixin,
    WritableNestedSerializer,
):
    class Meta:
        model = VMInterface
        fields = ("id", "url", "display", "name")
        brief_fields = ("id", "url", "display", "name")


class NestedDeviceRoleSerializer(
    RestrictedNestedObjectMixin,
    WritableNestedSerializer,
):
    class Meta:
        model = DeviceRole
        fields = ("id", "url", "display", "name")
        brief_fields = ("id", "url", "display", "name")


class NestedDeviceTypeSerializer(
    RestrictedNestedObjectMixin,
    WritableNestedSerializer,
):
    class Meta:
        model = DeviceType
        fields = ("id", "url", "display", "model")
        brief_fields = ("id", "url", "display", "model")


class NestedManufacturerSerializer(
    RestrictedNestedObjectMixin,
    WritableNestedSerializer,
):
    class Meta:
        model = Manufacturer
        fields = ("id", "url", "display", "name")
        brief_fields = ("id", "url", "display", "name")


class NestedSiteSerializer(RestrictedNestedObjectMixin, WritableNestedSerializer):
    class Meta:
        model = Site
        fields = ("id", "url", "display", "name")
        brief_fields = ("id", "url", "display", "name")


class NestedClusterTypeSerializer(
    RestrictedNestedObjectMixin,
    WritableNestedSerializer,
):
    class Meta:
        model = ClusterType
        fields = ("id", "url", "display", "name")
        brief_fields = ("id", "url", "display", "name")


SYNC_TRAILER_FIELDS = (
    "proxmox_last_updated",
    "last_updated",
    "last_run_id",
    "tags",
    "custom_fields",
    "created",
)

VM_PROXMOX_FIELDS = (
    "proxmox_vm_id",
    "proxmox_vm_type",
    "proxmox_start_at_boot",
    "proxmox_unprivileged_container",
    "proxmox_qemu_agent",
    "proxmox_search_domain",
    "proxmox_link",
    "proxmox_status",
    "proxmox_uptime",
    "proxmox_tags",
    "proxmox_os",
    "proxmox_storage",
    "proxmox_disk",
    "proxmox_interfaces",
    "proxmox_vmid",
    "proxmox_notes",
    "proxmox_tcp_states",
    "proxmox_cpu_type",
    "proxmox_storage_ids",
    "proxmox_storage_names",
    "proxmox_device_names",
    "proxmox_migration_duration",
    "proxmox_migration_type",
)

DEVICE_PROXMOX_FIELDS = (
    "proxmox_link",
    "proxmox_tags",
    "proxmox_os",
    "proxmox_storage",
    "proxmox_disk",
    "proxmox_interfaces",
    "proxmox_vmid",
    "proxmox_notes",
    "proxmox_tcp_states",
    "proxmox_cpu_type",
    "proxmox_storage_ids",
    "proxmox_storage_names",
    "proxmox_device_names",
    "hardware_chassis_serial",
    "hardware_chassis_manufacturer",
    "hardware_chassis_product",
)


class ProxboxVirtualMachineSyncStateSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxvirtualmachinesyncstate-detail",
    )
    virtual_machine = NestedVirtualMachineSerializer()
    endpoint = RestrictedNestedProxmoxEndpointSerializer(
        required=False,
        allow_null=True,
    )
    proxmox_node = RestrictedNestedProxmoxNodeSerializer(
        required=False,
        allow_null=True,
    )
    proxmox_cluster = RestrictedNestedProxmoxClusterSerializer(
        required=False,
        allow_null=True,
    )

    class Meta:
        model = ProxboxVirtualMachineSyncState
        fields = (
            "id",
            "url",
            "display",
            "virtual_machine",
            "endpoint",
            "proxmox_node",
            "proxmox_node_name",
            "proxmox_cluster",
            "proxmox_cluster_name",
            "proxmox_endpoint_raw_id",
            *VM_PROXMOX_FIELDS,
            *SYNC_TRAILER_FIELDS,
        )
        brief_fields = ("id", "url", "display", "virtual_machine", "proxmox_vm_id")


class ProxboxDeviceSyncStateSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxdevicesyncstate-detail",
    )
    device = NestedDeviceSerializer()
    endpoint = RestrictedNestedProxmoxEndpointSerializer(
        required=False,
        allow_null=True,
    )
    proxmox_node = RestrictedNestedProxmoxNodeSerializer(
        required=False,
        allow_null=True,
    )
    proxmox_cluster = RestrictedNestedProxmoxClusterSerializer(
        required=False,
        allow_null=True,
    )

    class Meta:
        model = ProxboxDeviceSyncState
        fields = (
            "id",
            "url",
            "display",
            "device",
            "endpoint",
            "proxmox_node",
            "proxmox_node_name",
            "proxmox_cluster",
            "proxmox_cluster_name",
            *DEVICE_PROXMOX_FIELDS,
            *SYNC_TRAILER_FIELDS,
        )
        brief_fields = ("id", "url", "display", "device", "proxmox_node_name")


class ProxboxClusterSyncStateSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxclustersyncstate-detail",
    )
    cluster = NestedClusterSerializer()
    proxmox_cluster = RestrictedNestedProxmoxClusterSerializer(
        required=False,
        allow_null=True,
    )

    class Meta:
        model = ProxboxClusterSyncState
        fields = (
            "id",
            "url",
            "display",
            "cluster",
            "proxmox_cluster",
            "proxmox_cluster_name",
            "proxmox_cluster_status",
            "proxmox_cluster_raw_id",
            *SYNC_TRAILER_FIELDS,
        )
        brief_fields = ("id", "url", "display", "cluster", "proxmox_cluster_name")


class ProxboxIPAddressSyncStateSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxipaddresssyncstate-detail",
    )
    ip_address = NestedIPAddressSerializer()

    class Meta:
        model = ProxboxIPAddressSyncState
        fields = (
            "id",
            "url",
            "display",
            "ip_address",
            "proxmox_interface",
            "proxmox_mac",
            "proxmox_ip_addresses",
            *SYNC_TRAILER_FIELDS,
        )
        brief_fields = ("id", "url", "display", "ip_address", "proxmox_interface")


class ProxboxInterfaceSyncStateSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxinterfacesyncstate-detail",
    )
    interface = NestedInterfaceSerializer()

    class Meta:
        model = ProxboxInterfaceSyncState
        fields = (
            "id",
            "url",
            "display",
            "interface",
            "nic_speed_gbps",
            "nic_duplex",
            "nic_link",
            *SYNC_TRAILER_FIELDS,
        )
        brief_fields = ("id", "url", "display", "interface", "nic_speed_gbps")


class ProxboxVLANSyncStateSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxvlansyncstate-detail",
    )
    vlan = NestedVLANSerializer()

    class Meta:
        model = ProxboxVLANSyncState
        fields = (
            "id",
            "url",
            "display",
            "vlan",
            "proxmox_vlan_id",
            *SYNC_TRAILER_FIELDS,
        )
        brief_fields = ("id", "url", "display", "vlan", "proxmox_vlan_id")


class ProxboxClusterGroupSyncStateSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxclustergroupsyncstate-detail",
    )
    cluster_group = NestedClusterGroupSerializer()

    class Meta:
        model = ProxboxClusterGroupSyncState
        fields = (
            "id",
            "url",
            "display",
            "cluster_group",
            "proxmox_cluster_name",
            "proxmox_cluster_status",
            *SYNC_TRAILER_FIELDS,
        )
        brief_fields = ("id", "url", "display", "cluster_group")


class ProxboxVirtualDiskSyncStateSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxvirtualdisksyncstate-detail",
    )
    virtual_disk = NestedVirtualDiskSerializer()

    class Meta:
        model = ProxboxVirtualDiskSyncState
        fields = (
            "id",
            "url",
            "display",
            "virtual_disk",
            "proxbox_storage_id",
            *SYNC_TRAILER_FIELDS,
        )
        brief_fields = ("id", "url", "display", "virtual_disk", "proxbox_storage_id")


class ProxboxVMInterfaceSyncStateSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxvminterfacesyncstate-detail",
    )
    vm_interface = NestedVMInterfaceSerializer()

    class Meta:
        model = ProxboxVMInterfaceSyncState
        fields = (
            "id",
            "url",
            "display",
            "vm_interface",
            "proxbox_bridge",
            *SYNC_TRAILER_FIELDS,
        )
        brief_fields = ("id", "url", "display", "vm_interface", "proxbox_bridge")


class ProxboxDeviceRoleSyncStateSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxdevicerolesyncstate-detail",
    )
    device_role = NestedDeviceRoleSerializer()

    class Meta:
        model = ProxboxDeviceRoleSyncState
        fields = ("id", "url", "display", "device_role", *SYNC_TRAILER_FIELDS)
        brief_fields = ("id", "url", "display", "device_role")


class ProxboxDeviceTypeSyncStateSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxdevicetypesyncstate-detail",
    )
    device_type = NestedDeviceTypeSerializer()

    class Meta:
        model = ProxboxDeviceTypeSyncState
        fields = ("id", "url", "display", "device_type", *SYNC_TRAILER_FIELDS)
        brief_fields = ("id", "url", "display", "device_type")


class ProxboxManufacturerSyncStateSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxmanufacturersyncstate-detail",
    )
    manufacturer = NestedManufacturerSerializer()

    class Meta:
        model = ProxboxManufacturerSyncState
        fields = ("id", "url", "display", "manufacturer", *SYNC_TRAILER_FIELDS)
        brief_fields = ("id", "url", "display", "manufacturer")


class ProxboxSiteSyncStateSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxsitesyncstate-detail",
    )
    site = NestedSiteSerializer()

    class Meta:
        model = ProxboxSiteSyncState
        fields = ("id", "url", "display", "site", *SYNC_TRAILER_FIELDS)
        brief_fields = ("id", "url", "display", "site")


class ProxboxClusterTypeSyncStateSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxclustertypesyncstate-detail",
    )
    cluster_type = NestedClusterTypeSerializer()

    class Meta:
        model = ProxboxClusterTypeSyncState
        fields = ("id", "url", "display", "cluster_type", *SYNC_TRAILER_FIELDS)
        brief_fields = ("id", "url", "display", "cluster_type")
