"""Table for Proxmox VM template records."""

from django_tables2 import tables

from netbox.tables import NetBoxTable

from netbox_proxbox.models import ProxmoxVMTemplate


class ProxmoxVMTemplateTable(NetBoxTable):
    """django-tables2 layout for Proxmox VM template list views."""

    name = tables.Column(linkify=True)
    proxmox_endpoint = tables.Column(linkify=True)
    cluster = tables.Column(linkify=True)
    node = tables.Column(linkify=True)
    source_vm = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = ProxmoxVMTemplate
        fields = (
            "pk",
            "id",
            "name",
            "vmid",
            "proxmox_endpoint",
            "cluster",
            "node",
            "node_name",
            "proxmox_type",
            "status",
            "vcpus",
            "memory",
            "disk",
            "source_vm",
            "cloud_init_enabled",
            "last_synced",
            "created",
            "last_updated",
        )
        default_columns = (
            "pk",
            "name",
            "vmid",
            "proxmox_endpoint",
            "cluster",
            "node_name",
            "proxmox_type",
            "status",
            "vcpus",
            "memory",
            "disk",
        )
