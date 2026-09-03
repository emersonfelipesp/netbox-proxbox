"""Table layout for virtual-machine intent rows."""

import django_tables2 as tables
from netbox.tables import NetBoxTable

from netbox_proxbox.models import ProxmoxVMIntent


class ProxmoxVMIntentTable(NetBoxTable):
    virtual_machine = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = ProxmoxVMIntent
        fields = (
            "pk",
            "virtual_machine",
            "target_node",
            "target_storage",
            "iso",
            "template_vmid",
            "swap",
            "rootfs",
            "ostemplate",
            "cloud_init_user",
            "intent_state",
            "last_apply_run_id",
            "actions",
        )
        default_columns = (
            "pk",
            "virtual_machine",
            "target_node",
            "target_storage",
            "template_vmid",
            "intent_state",
        )
