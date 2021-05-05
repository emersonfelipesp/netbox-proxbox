# tables.py
import django_tables2 as tables
from utilities.tables import BaseTable
from .models import ProxmoxVM


class ProxmoxVMTable(BaseTable):
    """Table for displaying BGP Peering objects."""

    id = tables.LinkColumn()
    cluster = tables.LinkColumn()
    virtual_machine = tables.LinkColumn()
    proxmox_vm_id = tables.LinkColumn()

    class Meta(BaseTable.Meta):
        model = ProxmoxVM
        fields = (
            "id",
            "virtual_machine",
            "proxmox_vm_id",
            "status",
            "type",
            "node",
            "cluster",
        )