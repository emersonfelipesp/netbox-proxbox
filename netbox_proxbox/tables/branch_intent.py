"""Table layout for plugin-owned branch intent rows."""

import django_tables2 as tables
from netbox.tables import NetBoxTable
from netbox.tables.columns import BooleanColumn

from netbox_proxbox.models import ProxboxBranchIntent


class ProxboxBranchIntentTable(NetBoxTable):
    """Display soft branch identity and both safety gates."""

    branch_id = tables.Column(linkify=True)
    apply_to_proxmox = BooleanColumn()
    apply_destroy_confirmed = BooleanColumn()

    class Meta(NetBoxTable.Meta):
        model = ProxboxBranchIntent
        fields = (
            "pk",
            "branch_id",
            "branch_schema_id",
            "apply_to_proxmox",
            "apply_destroy_confirmed",
            "actions",
        )
        default_columns = fields
