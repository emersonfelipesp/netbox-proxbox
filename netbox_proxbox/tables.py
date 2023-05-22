# tables.py
import django_tables2 as table

from netbox.tables import NetBoxTable
from .models import ProxmoxVM

class ProxmoxVMTable(NetBoxTable):
    """Table for displaying BGP Peering objects."""
    id = table.LinkColumn()
    cluster = table.LinkColumn()
    virtual_machine = table.LinkColumn()
    proxmox_vm_id = table.LinkColumn()

    class Meta(NetBoxTable.Meta):
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

class VMUpdateResult(table.Table):
    """Table for displaying VM/CT update results"""

    name = table.Column()
    status = table.Column(attrs={"span": {"class": "badge bg-green"}})
    custom_fields = table.Column(verbose_name = "Custom Fields")
    local_context = table.Column(verbose_name = "Local Context")
    resources = table.Column()
    tag = table.Column(attrs={"span": {"class": "badge bg-green"}})
    interfaces = table.Column()
    ips = table.Column(verbose_name = "IP Address")

    class Meta(NetBoxTable.Meta):
        fields = ('name', 'status', 'custom_fields', 'local_context', 'resources', 'tag', 'interfaces', 'ips')
        default_columns = ('name')
        #fields = ('name', 'status', 'custom_fields', 'local_context', 'resources', 'tag', 'result')
        #default_columns = ('name', 'status', 'custom_fields', 'local_context', 'resources', 'tag', 'result')


class NodeUpdateResult(table.Table):
    """Table for displaying VM/CT update results"""

    status = table.Column(attrs={"span": {"class": "badge bg-green"}})
    cluster = table.Column()
    interfaces = table.Column()
    result = table.Column()


    class Meta(NetBoxTable.Meta):
        fields = ('status', 'cluster', 'interfaces', 'result')
        default_columns = ('name')