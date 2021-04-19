# tables.py
import django_tables2 as tables
from utilities.tables import BaseTable
from .models import VmResources


class VmResourcesTable(BaseTable):
    """Table for displaying BGP Peering objects."""

    id = tables.LinkColumn()
    cluster = tables.LinkColumn()
    virtual_machine = tables.LinkColumn()
    proxmox_vm_id = tables.LinkColumn()

    class Meta(BaseTable.Meta):
        model = VmResources
        fields = (
            "id",
            "cluster",
            "node",
            "virtual_machine",
            "proxmox_vm_id",
            "status",
            "type",
        )