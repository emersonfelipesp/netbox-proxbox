"""Add typed Proxbox sync-state sidecars for legacy custom-field payloads."""

from __future__ import annotations

import django.db.models.deletion
import netbox.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import create_model_idempotent


BASES = (netbox.models.deletion.DeleteMixin, models.Model)


def base_fields():
    return [
        (
            "id",
            models.BigAutoField(auto_created=True, primary_key=True, serialize=False),
        ),
        ("created", models.DateTimeField(auto_now_add=True, null=True)),
        (
            "last_updated",
            models.DateTimeField(
                auto_now=True,
                blank=True,
                null=True,
            ),
        ),
        (
            "proxmox_last_updated",
            models.DateTimeField(
                blank=True,
                db_index=True,
                help_text=(
                    "Timestamp mirrored from the legacy proxmox_last_updated "
                    "custom field."
                ),
                null=True,
            ),
        ),
        (
            "custom_field_data",
            models.JSONField(
                blank=True,
                default=dict,
                encoder=utilities.json.CustomFieldJSONEncoder,
            ),
        ),
        (
            "last_run_id",
            models.CharField(
                blank=True,
                help_text="proxbox-api run identifier mirrored from proxbox_last_run_id.",
                max_length=255,
            ),
        ),
        (
            "tags",
            taggit.managers.TaggableManager(
                through="extras.TaggedItem",
                to="extras.Tag",
            ),
        ),
    ]


def endpoint_field(related_name):
    return (
        "endpoint",
        models.ForeignKey(
            blank=True,
            null=True,
            on_delete=django.db.models.deletion.SET_NULL,
            related_name=related_name,
            to="netbox_proxbox.proxmoxendpoint",
        ),
    )


def node_field(related_name):
    return (
        "proxmox_node",
        models.ForeignKey(
            blank=True,
            null=True,
            on_delete=django.db.models.deletion.SET_NULL,
            related_name=related_name,
            to="netbox_proxbox.proxmoxnode",
        ),
    )


def cluster_field(related_name):
    return (
        "proxmox_cluster",
        models.ForeignKey(
            blank=True,
            null=True,
            on_delete=django.db.models.deletion.SET_NULL,
            related_name=related_name,
            to="netbox_proxbox.proxmoxcluster",
        ),
    )


VM_PROXMOX_FIELDS = [
    ("proxmox_vm_id", models.IntegerField(blank=True, null=True)),
    ("proxmox_vm_type", models.CharField(blank=True, max_length=64)),
    ("proxmox_start_at_boot", models.BooleanField(blank=True, null=True)),
    ("proxmox_unprivileged_container", models.BooleanField(blank=True, null=True)),
    ("proxmox_qemu_agent", models.BooleanField(blank=True, null=True)),
    ("proxmox_search_domain", models.CharField(blank=True, max_length=255)),
    ("proxmox_link", models.URLField(blank=True, max_length=500)),
    ("proxmox_status", models.CharField(blank=True, max_length=64)),
    ("proxmox_uptime", models.IntegerField(blank=True, null=True)),
    ("proxmox_tags", models.TextField(blank=True)),
    ("proxmox_os", models.CharField(blank=True, max_length=255)),
    ("proxmox_storage", models.CharField(blank=True, max_length=255)),
    ("proxmox_disk", models.CharField(blank=True, max_length=255)),
    ("proxmox_interfaces", models.TextField(blank=True)),
    ("proxmox_vmid", models.CharField(blank=True, max_length=64)),
    ("proxmox_notes", models.TextField(blank=True)),
    ("proxmox_tcp_states", models.TextField(blank=True)),
    ("proxmox_cpu_type", models.CharField(blank=True, max_length=255)),
    ("proxmox_storage_ids", models.TextField(blank=True)),
    ("proxmox_storage_names", models.TextField(blank=True)),
    ("proxmox_device_names", models.TextField(blank=True)),
    ("proxmox_migration_duration", models.IntegerField(blank=True, null=True)),
    ("proxmox_migration_type", models.CharField(blank=True, max_length=64)),
]

DEVICE_PROXMOX_FIELDS = [
    ("proxmox_link", models.URLField(blank=True, max_length=500)),
    ("proxmox_tags", models.TextField(blank=True)),
    ("proxmox_os", models.CharField(blank=True, max_length=255)),
    ("proxmox_storage", models.CharField(blank=True, max_length=255)),
    ("proxmox_disk", models.CharField(blank=True, max_length=255)),
    ("proxmox_interfaces", models.TextField(blank=True)),
    ("proxmox_vmid", models.CharField(blank=True, max_length=64)),
    ("proxmox_notes", models.TextField(blank=True)),
    ("proxmox_tcp_states", models.TextField(blank=True)),
    ("proxmox_cpu_type", models.CharField(blank=True, max_length=255)),
    ("proxmox_storage_ids", models.TextField(blank=True)),
    ("proxmox_storage_names", models.TextField(blank=True)),
    ("proxmox_device_names", models.TextField(blank=True)),
    ("hardware_chassis_serial", models.CharField(blank=True, max_length=255)),
    ("hardware_chassis_manufacturer", models.CharField(blank=True, max_length=255)),
    ("hardware_chassis_product", models.CharField(blank=True, max_length=255)),
]


class Migration(migrations.Migration):
    dependencies = [
        ("dcim", "0227_alter_interface_speed_bigint"),
        ("ipam", "0076_natural_ordering"),
        ("netbox_proxbox", "0064_proxmoxvmcloudinit_intent"),
        ("virtualization", "0052_gfk_indexes"),
    ]

    operations = [
        create_model_idempotent(
            name="ProxboxVirtualMachineSyncState",
            fields=[
                *base_fields(),
                (
                    "virtual_machine",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxbox_sync_state",
                        to="virtualization.virtualmachine",
                    ),
                ),
                endpoint_field("virtual_machine_sync_states"),
                node_field("virtual_machine_sync_states"),
                ("proxmox_node_name", models.CharField(blank=True, max_length=255)),
                cluster_field("virtual_machine_sync_states"),
                ("proxmox_cluster_name", models.CharField(blank=True, max_length=255)),
                (
                    "proxmox_endpoint_raw_id",
                    models.IntegerField(blank=True, null=True),
                ),
                *VM_PROXMOX_FIELDS,
            ],
            options={
                "ordering": ("virtual_machine",),
                "verbose_name": "Proxbox virtual machine sync state",
                "verbose_name_plural": "Proxbox virtual machine sync states",
            },
            bases=BASES,
        ),
        create_model_idempotent(
            name="ProxboxDeviceSyncState",
            fields=[
                *base_fields(),
                (
                    "device",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxbox_sync_state",
                        to="dcim.device",
                    ),
                ),
                endpoint_field("device_sync_states"),
                node_field("device_sync_states"),
                ("proxmox_node_name", models.CharField(blank=True, max_length=255)),
                cluster_field("device_sync_states"),
                ("proxmox_cluster_name", models.CharField(blank=True, max_length=255)),
                *DEVICE_PROXMOX_FIELDS,
            ],
            options={
                "ordering": ("device",),
                "verbose_name": "Proxbox device sync state",
                "verbose_name_plural": "Proxbox device sync states",
            },
            bases=BASES,
        ),
        create_model_idempotent(
            name="ProxboxClusterSyncState",
            fields=[
                *base_fields(),
                (
                    "cluster",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxbox_sync_state",
                        to="virtualization.cluster",
                    ),
                ),
                cluster_field("cluster_sync_states"),
                ("proxmox_cluster_name", models.CharField(blank=True, max_length=255)),
                (
                    "proxmox_cluster_status",
                    models.CharField(blank=True, max_length=64),
                ),
                (
                    "proxmox_cluster_raw_id",
                    models.IntegerField(blank=True, null=True),
                ),
            ],
            options={
                "ordering": ("cluster",),
                "verbose_name": "Proxbox cluster sync state",
                "verbose_name_plural": "Proxbox cluster sync states",
            },
            bases=BASES,
        ),
        create_model_idempotent(
            name="ProxboxIPAddressSyncState",
            fields=[
                *base_fields(),
                (
                    "ip_address",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxbox_sync_state",
                        to="ipam.ipaddress",
                    ),
                ),
                ("proxmox_interface", models.CharField(blank=True, max_length=255)),
                ("proxmox_mac", models.CharField(blank=True, max_length=64)),
                ("proxmox_ip_addresses", models.TextField(blank=True)),
            ],
            options={
                "ordering": ("ip_address",),
                "verbose_name": "Proxbox IP address sync state",
                "verbose_name_plural": "Proxbox IP address sync states",
            },
            bases=BASES,
        ),
        create_model_idempotent(
            name="ProxboxInterfaceSyncState",
            fields=[
                *base_fields(),
                (
                    "interface",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxbox_sync_state",
                        to="dcim.interface",
                    ),
                ),
                ("nic_speed_gbps", models.IntegerField(blank=True, null=True)),
                ("nic_duplex", models.CharField(blank=True, max_length=64)),
                ("nic_link", models.BooleanField(blank=True, null=True)),
            ],
            options={
                "ordering": ("interface",),
                "verbose_name": "Proxbox interface sync state",
                "verbose_name_plural": "Proxbox interface sync states",
            },
            bases=BASES,
        ),
        create_model_idempotent(
            name="ProxboxVLANSyncState",
            fields=[
                *base_fields(),
                (
                    "vlan",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxbox_sync_state",
                        to="ipam.vlan",
                    ),
                ),
                ("proxmox_vlan_id", models.IntegerField(blank=True, null=True)),
            ],
            options={
                "ordering": ("vlan",),
                "verbose_name": "Proxbox VLAN sync state",
                "verbose_name_plural": "Proxbox VLAN sync states",
            },
            bases=BASES,
        ),
        create_model_idempotent(
            name="ProxboxClusterGroupSyncState",
            fields=[
                *base_fields(),
                (
                    "cluster_group",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxbox_sync_state",
                        to="virtualization.clustergroup",
                    ),
                ),
                ("proxmox_cluster_name", models.CharField(blank=True, max_length=255)),
                (
                    "proxmox_cluster_status",
                    models.CharField(blank=True, max_length=64),
                ),
            ],
            options={
                "ordering": ("cluster_group",),
                "verbose_name": "Proxbox cluster group sync state",
                "verbose_name_plural": "Proxbox cluster group sync states",
            },
            bases=BASES,
        ),
        create_model_idempotent(
            name="ProxboxVirtualDiskSyncState",
            fields=[
                *base_fields(),
                (
                    "virtual_disk",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxbox_sync_state",
                        to="virtualization.virtualdisk",
                    ),
                ),
                ("proxbox_storage_id", models.JSONField(blank=True, null=True)),
            ],
            options={
                "ordering": ("virtual_disk",),
                "verbose_name": "Proxbox virtual disk sync state",
                "verbose_name_plural": "Proxbox virtual disk sync states",
            },
            bases=BASES,
        ),
        create_model_idempotent(
            name="ProxboxVMInterfaceSyncState",
            fields=[
                *base_fields(),
                (
                    "vm_interface",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxbox_sync_state",
                        to="virtualization.vminterface",
                    ),
                ),
                ("proxbox_bridge", models.JSONField(blank=True, null=True)),
            ],
            options={
                "ordering": ("vm_interface",),
                "verbose_name": "Proxbox VM interface sync state",
                "verbose_name_plural": "Proxbox VM interface sync states",
            },
            bases=BASES,
        ),
        create_model_idempotent(
            name="ProxboxDeviceRoleSyncState",
            fields=[
                *base_fields(),
                (
                    "device_role",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxbox_sync_state",
                        to="dcim.devicerole",
                    ),
                ),
            ],
            options={
                "ordering": ("device_role",),
                "verbose_name": "Proxbox device role sync state",
                "verbose_name_plural": "Proxbox device role sync states",
            },
            bases=BASES,
        ),
        create_model_idempotent(
            name="ProxboxDeviceTypeSyncState",
            fields=[
                *base_fields(),
                (
                    "device_type",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxbox_sync_state",
                        to="dcim.devicetype",
                    ),
                ),
            ],
            options={
                "ordering": ("device_type",),
                "verbose_name": "Proxbox device type sync state",
                "verbose_name_plural": "Proxbox device type sync states",
            },
            bases=BASES,
        ),
        create_model_idempotent(
            name="ProxboxManufacturerSyncState",
            fields=[
                *base_fields(),
                (
                    "manufacturer",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxbox_sync_state",
                        to="dcim.manufacturer",
                    ),
                ),
            ],
            options={
                "ordering": ("manufacturer",),
                "verbose_name": "Proxbox manufacturer sync state",
                "verbose_name_plural": "Proxbox manufacturer sync states",
            },
            bases=BASES,
        ),
        create_model_idempotent(
            name="ProxboxSiteSyncState",
            fields=[
                *base_fields(),
                (
                    "site",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxbox_sync_state",
                        to="dcim.site",
                    ),
                ),
            ],
            options={
                "ordering": ("site",),
                "verbose_name": "Proxbox site sync state",
                "verbose_name_plural": "Proxbox site sync states",
            },
            bases=BASES,
        ),
        create_model_idempotent(
            name="ProxboxClusterTypeSyncState",
            fields=[
                *base_fields(),
                (
                    "cluster_type",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxbox_sync_state",
                        to="virtualization.clustertype",
                    ),
                ),
            ],
            options={
                "ordering": ("cluster_type",),
                "verbose_name": "Proxbox cluster type sync state",
                "verbose_name_plural": "Proxbox cluster type sync states",
            },
            bases=BASES,
        ),
    ]
