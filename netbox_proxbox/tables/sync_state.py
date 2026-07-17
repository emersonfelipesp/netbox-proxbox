"""Tables for typed Proxbox sync-state sidecar models."""

import django_tables2 as tables
from django.utils.translation import gettext as _

from netbox.tables import NetBoxTable
from netbox.tables.columns import BooleanColumn

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


class ProxboxVirtualMachineSyncStateTable(NetBoxTable):
    virtual_machine = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)
    proxmox_node = tables.Column(linkify=True)
    proxmox_cluster = tables.Column(linkify=True)
    proxmox_start_at_boot = BooleanColumn(verbose_name=_("Start at boot"))
    proxmox_qemu_agent = BooleanColumn(verbose_name=_("QEMU agent"))

    class Meta(NetBoxTable.Meta):
        model = ProxboxVirtualMachineSyncState
        fields = (
            "pk",
            "id",
            "virtual_machine",
            "endpoint",
            "proxmox_node",
            "proxmox_node_name",
            "proxmox_cluster",
            "proxmox_cluster_name",
            "proxmox_vm_id",
            "proxmox_vm_type",
            "proxmox_status",
            "proxmox_start_at_boot",
            "proxmox_qemu_agent",
            "proxmox_last_updated",
            "last_run_id",
            "actions",
        )
        default_columns = (
            "pk",
            "virtual_machine",
            "endpoint",
            "proxmox_node",
            "proxmox_cluster",
            "proxmox_vm_id",
            "proxmox_status",
            "proxmox_last_updated",
        )


class ProxboxDeviceSyncStateTable(NetBoxTable):
    device = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)
    proxmox_node = tables.Column(linkify=True)
    proxmox_cluster = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = ProxboxDeviceSyncState
        fields = (
            "pk",
            "id",
            "device",
            "endpoint",
            "proxmox_node",
            "proxmox_node_name",
            "proxmox_cluster",
            "proxmox_cluster_name",
            "proxmox_vmid",
            "hardware_chassis_serial",
            "hardware_chassis_manufacturer",
            "hardware_chassis_product",
            "proxmox_last_updated",
            "last_run_id",
            "actions",
        )
        default_columns = (
            "pk",
            "device",
            "endpoint",
            "proxmox_node",
            "proxmox_cluster",
            "proxmox_vmid",
            "proxmox_last_updated",
        )


class ProxboxClusterSyncStateTable(NetBoxTable):
    cluster = tables.Column(linkify=True)
    proxmox_cluster = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = ProxboxClusterSyncState
        fields = (
            "pk",
            "id",
            "cluster",
            "proxmox_cluster",
            "proxmox_cluster_name",
            "proxmox_cluster_status",
            "proxmox_cluster_raw_id",
            "proxmox_last_updated",
            "last_run_id",
            "actions",
        )
        default_columns = (
            "pk",
            "cluster",
            "proxmox_cluster",
            "proxmox_cluster_name",
            "proxmox_cluster_status",
            "proxmox_last_updated",
        )


class ProxboxIPAddressSyncStateTable(NetBoxTable):
    ip_address = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = ProxboxIPAddressSyncState
        fields = (
            "pk",
            "id",
            "ip_address",
            "proxmox_interface",
            "proxmox_mac",
            "proxmox_ip_addresses",
            "proxmox_last_updated",
            "actions",
        )
        default_columns = (
            "pk",
            "ip_address",
            "proxmox_interface",
            "proxmox_mac",
            "proxmox_last_updated",
        )


class ProxboxInterfaceSyncStateTable(NetBoxTable):
    interface = tables.Column(linkify=True)
    nic_link = BooleanColumn(verbose_name=_("Link"))

    class Meta(NetBoxTable.Meta):
        model = ProxboxInterfaceSyncState
        fields = (
            "pk",
            "id",
            "interface",
            "nic_speed_gbps",
            "nic_duplex",
            "nic_link",
            "proxmox_last_updated",
            "actions",
        )
        default_columns = (
            "pk",
            "interface",
            "nic_speed_gbps",
            "nic_duplex",
            "nic_link",
            "proxmox_last_updated",
        )


class ProxboxVLANSyncStateTable(NetBoxTable):
    vlan = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = ProxboxVLANSyncState
        fields = (
            "pk",
            "id",
            "vlan",
            "proxmox_vlan_id",
            "proxmox_last_updated",
            "actions",
        )
        default_columns = ("pk", "vlan", "proxmox_vlan_id", "proxmox_last_updated")


class ProxboxClusterGroupSyncStateTable(NetBoxTable):
    cluster_group = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = ProxboxClusterGroupSyncState
        fields = (
            "pk",
            "id",
            "cluster_group",
            "proxmox_cluster_name",
            "proxmox_cluster_status",
            "proxmox_last_updated",
            "actions",
        )
        default_columns = (
            "pk",
            "cluster_group",
            "proxmox_cluster_name",
            "proxmox_cluster_status",
        )


class ProxboxVirtualDiskSyncStateTable(NetBoxTable):
    virtual_disk = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = ProxboxVirtualDiskSyncState
        fields = (
            "pk",
            "id",
            "virtual_disk",
            "proxbox_storage_id",
            "proxmox_last_updated",
            "actions",
        )
        default_columns = (
            "pk",
            "virtual_disk",
            "proxbox_storage_id",
            "proxmox_last_updated",
        )


class ProxboxVMInterfaceSyncStateTable(NetBoxTable):
    vm_interface = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = ProxboxVMInterfaceSyncState
        fields = (
            "pk",
            "id",
            "vm_interface",
            "proxbox_bridge",
            "proxmox_last_updated",
            "actions",
        )
        default_columns = (
            "pk",
            "vm_interface",
            "proxbox_bridge",
            "proxmox_last_updated",
        )


class ProxboxDeviceRoleSyncStateTable(NetBoxTable):
    device_role = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = ProxboxDeviceRoleSyncState
        fields = ("pk", "id", "device_role", "proxmox_last_updated", "actions")
        default_columns = ("pk", "device_role", "proxmox_last_updated")


class ProxboxDeviceTypeSyncStateTable(NetBoxTable):
    device_type = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = ProxboxDeviceTypeSyncState
        fields = ("pk", "id", "device_type", "proxmox_last_updated", "actions")
        default_columns = ("pk", "device_type", "proxmox_last_updated")


class ProxboxManufacturerSyncStateTable(NetBoxTable):
    manufacturer = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = ProxboxManufacturerSyncState
        fields = ("pk", "id", "manufacturer", "proxmox_last_updated", "actions")
        default_columns = ("pk", "manufacturer", "proxmox_last_updated")


class ProxboxSiteSyncStateTable(NetBoxTable):
    site = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = ProxboxSiteSyncState
        fields = ("pk", "id", "site", "proxmox_last_updated", "actions")
        default_columns = ("pk", "site", "proxmox_last_updated")


class ProxboxClusterTypeSyncStateTable(NetBoxTable):
    cluster_type = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = ProxboxClusterTypeSyncState
        fields = ("pk", "id", "cluster_type", "proxmox_last_updated", "actions")
        default_columns = ("pk", "cluster_type", "proxmox_last_updated")
