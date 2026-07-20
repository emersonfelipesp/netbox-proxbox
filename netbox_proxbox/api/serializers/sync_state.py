"""API serializers for typed Proxbox sync-state sidecar models."""

from __future__ import annotations

from django.core.exceptions import FieldDoesNotExist
from django.db import IntegrityError, transaction
from dcim.models import Device, DeviceRole, DeviceType, Interface, Manufacturer, Site
from ipam.models import IPAddress, VLAN
from netbox.api.serializers import NetBoxModelSerializer, WritableNestedSerializer
from rest_framework import serializers
from rest_framework.exceptions import APIException
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
from netbox_proxbox.api.serializers.storage import NestedProxmoxStorageSerializer
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


class SyncStateConflict(APIException):
    status_code = 409
    default_detail = "The target parent already has a Proxbox sync-state row."
    default_code = "sync_state_conflict"


class RestrictedNestedObjectMixin:
    """Resolve writable nested objects through the caller's view permissions."""

    def _restricted_queryset(self):
        queryset = self.Meta.model.objects.all()
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is not None and hasattr(queryset, "restrict"):
            queryset = queryset.restrict(user, "view")
        return queryset

    def to_internal_value(self, data):
        return get_related_object_by_attrs(self._restricted_queryset(), data)

    def to_representation(self, instance):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if (
            instance is not None
            and user is not None
            and not getattr(user, "is_superuser", False)
        ):
            cache = self.context.setdefault("_proxbox_nested_visibility_cache", {})
            cache_key = (
                self.Meta.model._meta.label_lower,
                getattr(user, "pk", None),
                instance.pk,
            )
            queryset = self._restricted_queryset()
            if cache_key not in cache:
                cache[cache_key] = queryset.filter(pk=instance.pk).exists()
            if not cache[cache_key]:
                return None
        return super().to_representation(instance)


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


class RestrictedNestedProxmoxStorageSerializer(
    RestrictedNestedObjectMixin,
    NestedProxmoxStorageSerializer,
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


class ProxboxSyncStateSerializerMixin:
    """Shared write validation for one-to-one sync-state sidecars."""

    parent_field_name: str

    def _validate_parent_uniqueness(self, attrs: dict) -> None:
        parent_field = self.parent_field_name
        parent = attrs.get(parent_field)
        if self.instance is not None:
            current_parent = getattr(self.instance, parent_field)
            if parent is not None and parent.pk != current_parent.pk:
                if self.Meta.model.objects.filter(**{parent_field: parent}).exists():
                    raise SyncStateConflict(
                        {
                            parent_field: (
                                "This object already has a Proxbox sync-state row."
                            )
                        }
                    )
                raise serializers.ValidationError(
                    {parent_field: "The sync-state parent cannot be changed."}
                )
            parent = current_parent
        if parent is None:
            return
        queryset = self.Meta.model.objects.filter(**{parent_field: parent})
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise SyncStateConflict(
                {parent_field: "This object already has a Proxbox sync-state row."}
            )

    def _validate_relation_coherence(self, attrs: dict) -> None:
        relation_fields = {"endpoint", "proxmox_node", "proxmox_cluster"}
        available_relation_fields = set()
        for field in relation_fields:
            try:
                self.Meta.model._meta.get_field(field)
            except FieldDoesNotExist:
                continue
            available_relation_fields.add(field)
        if not relation_fields.intersection(attrs):
            return

        endpoint = (
            attrs.get("endpoint", getattr(self.instance, "endpoint", None))
            if "endpoint" in available_relation_fields
            else None
        )
        node = (
            attrs.get("proxmox_node", getattr(self.instance, "proxmox_node", None))
            if "proxmox_node" in available_relation_fields
            else None
        )
        cluster = (
            attrs.get(
                "proxmox_cluster",
                getattr(self.instance, "proxmox_cluster", None),
            )
            if "proxmox_cluster" in available_relation_fields
            else None
        )
        parent = attrs.get(
            self.parent_field_name,
            getattr(self.instance, self.parent_field_name, None),
        )
        errors = {}

        if node is not None:
            if (
                self.parent_field_name == "device"
                and parent is not None
                and node.netbox_device_id != parent.pk
            ):
                errors["proxmox_node"] = (
                    "Proxmox node must be linked to the sync-state device."
                )
            elif endpoint is not None and node.endpoint_id != endpoint.pk:
                errors["proxmox_node"] = (
                    "Node endpoint must match the sync-state endpoint."
                )
            else:
                endpoint = node.endpoint
                if "endpoint" in available_relation_fields:
                    attrs["endpoint"] = endpoint
            node_cluster = getattr(node, "proxmox_cluster", None)
            if node_cluster is not None:
                if cluster is not None and cluster.pk != node_cluster.pk:
                    errors["proxmox_cluster"] = (
                        "Cluster must match the selected node's Proxmox cluster."
                    )
                elif cluster is None and "proxmox_cluster" in available_relation_fields:
                    cluster = node_cluster
                    attrs["proxmox_cluster"] = cluster

        if cluster is not None:
            if (
                self.parent_field_name == "cluster"
                and parent is not None
                and cluster.netbox_cluster_id != parent.pk
            ):
                errors["proxmox_cluster"] = (
                    "Proxmox cluster must be linked to the sync-state cluster."
                )
            elif endpoint is not None and cluster.endpoint_id != endpoint.pk:
                errors["proxmox_cluster"] = (
                    "Cluster endpoint must match the sync-state endpoint."
                )
            else:
                endpoint = cluster.endpoint
                if "endpoint" in available_relation_fields:
                    attrs["endpoint"] = endpoint

        if errors:
            raise serializers.ValidationError(errors)

    def validate(self, attrs: dict) -> dict:
        attrs = super().validate(attrs)
        self._validate_parent_uniqueness(attrs)
        self._validate_relation_coherence(attrs)
        return attrs

    def create(self, validated_data: dict):
        try:
            with transaction.atomic():
                return super().create(validated_data)
        except IntegrityError as exc:
            raise SyncStateConflict() from exc

    def update(self, instance, validated_data: dict):
        try:
            with transaction.atomic():
                return super().update(instance, validated_data)
        except IntegrityError as exc:
            raise SyncStateConflict() from exc


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


class ProxboxVirtualMachineSyncStateSerializer(
    ProxboxSyncStateSerializerMixin,
    NetBoxModelSerializer,
):
    parent_field_name = "virtual_machine"
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


class ProxboxDeviceSyncStateSerializer(
    ProxboxSyncStateSerializerMixin,
    NetBoxModelSerializer,
):
    parent_field_name = "device"
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


class ProxboxClusterSyncStateSerializer(
    ProxboxSyncStateSerializerMixin,
    NetBoxModelSerializer,
):
    parent_field_name = "cluster"
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


class ProxboxIPAddressSyncStateSerializer(
    ProxboxSyncStateSerializerMixin,
    NetBoxModelSerializer,
):
    parent_field_name = "ip_address"
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


class ProxboxInterfaceSyncStateSerializer(
    ProxboxSyncStateSerializerMixin,
    NetBoxModelSerializer,
):
    parent_field_name = "interface"
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


class ProxboxVLANSyncStateSerializer(
    ProxboxSyncStateSerializerMixin,
    NetBoxModelSerializer,
):
    parent_field_name = "vlan"
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


class ProxboxClusterGroupSyncStateSerializer(
    ProxboxSyncStateSerializerMixin,
    NetBoxModelSerializer,
):
    parent_field_name = "cluster_group"
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


class ProxboxVirtualDiskSyncStateSerializer(
    ProxboxSyncStateSerializerMixin,
    NetBoxModelSerializer,
):
    parent_field_name = "virtual_disk"
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxvirtualdisksyncstate-detail",
    )
    virtual_disk = NestedVirtualDiskSerializer()
    proxbox_storage = RestrictedNestedProxmoxStorageSerializer(
        required=False,
        allow_null=True,
    )
    proxbox_storage_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProxboxVirtualDiskSyncState
        fields = (
            "id",
            "url",
            "display",
            "virtual_disk",
            "proxbox_storage",
            "proxbox_storage_id",
            "proxbox_storage_raw_id",
            "proxbox_storage_raw_value",
            *SYNC_TRAILER_FIELDS,
        )
        brief_fields = ("id", "url", "display", "virtual_disk", "proxbox_storage_id")


class ProxboxVMInterfaceSyncStateSerializer(
    ProxboxSyncStateSerializerMixin,
    NetBoxModelSerializer,
):
    parent_field_name = "vm_interface"
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxvminterfacesyncstate-detail",
    )
    vm_interface = NestedVMInterfaceSerializer()
    proxbox_bridge = NestedInterfaceSerializer(required=False, allow_null=True)

    class Meta:
        model = ProxboxVMInterfaceSyncState
        fields = (
            "id",
            "url",
            "display",
            "vm_interface",
            "proxbox_bridge",
            "proxbox_bridge_raw_id",
            "proxbox_bridge_raw_value",
            *SYNC_TRAILER_FIELDS,
        )
        brief_fields = ("id", "url", "display", "vm_interface", "proxbox_bridge")


class ProxboxDeviceRoleSyncStateSerializer(
    ProxboxSyncStateSerializerMixin,
    NetBoxModelSerializer,
):
    parent_field_name = "device_role"
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxdevicerolesyncstate-detail",
    )
    device_role = NestedDeviceRoleSerializer()

    class Meta:
        model = ProxboxDeviceRoleSyncState
        fields = ("id", "url", "display", "device_role", *SYNC_TRAILER_FIELDS)
        brief_fields = ("id", "url", "display", "device_role")


class ProxboxDeviceTypeSyncStateSerializer(
    ProxboxSyncStateSerializerMixin,
    NetBoxModelSerializer,
):
    parent_field_name = "device_type"
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxdevicetypesyncstate-detail",
    )
    device_type = NestedDeviceTypeSerializer()

    class Meta:
        model = ProxboxDeviceTypeSyncState
        fields = ("id", "url", "display", "device_type", *SYNC_TRAILER_FIELDS)
        brief_fields = ("id", "url", "display", "device_type")


class ProxboxManufacturerSyncStateSerializer(
    ProxboxSyncStateSerializerMixin,
    NetBoxModelSerializer,
):
    parent_field_name = "manufacturer"
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxmanufacturersyncstate-detail",
    )
    manufacturer = NestedManufacturerSerializer()

    class Meta:
        model = ProxboxManufacturerSyncState
        fields = ("id", "url", "display", "manufacturer", *SYNC_TRAILER_FIELDS)
        brief_fields = ("id", "url", "display", "manufacturer")


class ProxboxSiteSyncStateSerializer(
    ProxboxSyncStateSerializerMixin,
    NetBoxModelSerializer,
):
    parent_field_name = "site"
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxsitesyncstate-detail",
    )
    site = NestedSiteSerializer()

    class Meta:
        model = ProxboxSiteSyncState
        fields = ("id", "url", "display", "site", *SYNC_TRAILER_FIELDS)
        brief_fields = ("id", "url", "display", "site")


class ProxboxClusterTypeSyncStateSerializer(
    ProxboxSyncStateSerializerMixin,
    NetBoxModelSerializer,
):
    parent_field_name = "cluster_type"
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxclustertypesyncstate-detail",
    )
    cluster_type = NestedClusterTypeSerializer()

    class Meta:
        model = ProxboxClusterTypeSyncState
        fields = ("id", "url", "display", "cluster_type", *SYNC_TRAILER_FIELDS)
        brief_fields = ("id", "url", "display", "cluster_type")
