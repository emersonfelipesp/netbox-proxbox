"""Plugin-wide constants shared across models, forms, serializers, and sync code."""

from __future__ import annotations

SYNC_MODE_FIELD_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Virtual Machine",
        (
            "sync_mode_vm",
            "sync_mode_vm_template",
        ),
    ),
    (
        "VM Interface",
        (
            "sync_mode_vm_interface",
            "sync_mode_mac",
            "sync_mode_ip_address",
        ),
    ),
    (
        "Infrastructure",
        (
            "sync_mode_cluster",
            "sync_mode_node",
            "sync_mode_storage",
            "sync_mode_sdn",
            "sync_mode_sdn_bgp",
        ),
    ),
)

SYNC_MODE_FIELDS: tuple[str, ...] = tuple(
    field for _, fields in SYNC_MODE_FIELD_GROUPS for field in fields
)

SYNC_MODE_RESOURCE_TYPES: tuple[str, ...] = tuple(
    field.removeprefix("sync_mode_") for field in SYNC_MODE_FIELDS
)

SYNC_MODE_HIERARCHY: dict[str, str] = {
    "node": "cluster",
    "vm_interface": "vm",
    "ip_address": "vm_interface",
    "mac": "vm_interface",
    "sdn_bgp": "sdn",
}

OVERWRITE_FIELD_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Device",
        (
            "overwrite_device_role",
            "overwrite_device_type",
            "overwrite_device_tags",
            "overwrite_device_status",
            "overwrite_device_description",
            "overwrite_device_custom_fields",
        ),
    ),
    (
        "Virtual Machine",
        (
            "overwrite_vm_role",
            "overwrite_vm_type",
            "overwrite_vm_tags",
            "overwrite_vm_proxmox_tags",
            "overwrite_vm_description",
            "overwrite_vm_custom_fields",
            "overwrite_vm_cloudinit",
        ),
    ),
    (
        "Cluster",
        (
            "overwrite_cluster_tags",
            "overwrite_cluster_description",
            "overwrite_cluster_custom_fields",
        ),
    ),
    (
        "Node Interface",
        (
            "overwrite_node_interface_tags",
            "overwrite_node_interface_custom_fields",
        ),
    ),
    (
        "Storage",
        ("overwrite_storage_tags",),
    ),
    (
        "VM Interface",
        (
            "overwrite_vm_interface_tags",
            "overwrite_vm_interface_custom_fields",
        ),
    ),
    (
        "IP Address",
        (
            "overwrite_ip_status",
            "overwrite_ip_tags",
            "overwrite_ip_custom_fields",
            "overwrite_ip_address_dns_name",
        ),
    ),
)

OVERWRITE_FIELDS: tuple[str, ...] = tuple(
    field for _, fields in OVERWRITE_FIELD_GROUPS for field in fields
)
