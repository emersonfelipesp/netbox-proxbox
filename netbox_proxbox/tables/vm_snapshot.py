"""Define the NetBox table used to render VM snapshot records."""

from django_tables2 import tables
from django.utils.translation import gettext as _

from netbox.tables import NetBoxTable, ChoiceFieldColumn

from netbox_proxbox.models import VMSnapshot


class VMSnapshotTable(NetBoxTable):
    """django-tables2 layout for VM snapshot list views."""

    storage = tables.Column(linkify=True)
    virtual_machine = tables.Column(linkify=True)
    proxmox_storage = tables.Column(linkify=True)
    subtype = ChoiceFieldColumn(
        verbose_name=_("Subtype"),
    )
    status = ChoiceFieldColumn(
        verbose_name=_("Status"),
    )
    snaptime = tables.Column(
        verbose_name=_("Snapshot Time"),
    )

    class Meta(NetBoxTable.Meta):
        model = VMSnapshot
        fields = (
            "pk",
            "id",
            "proxmox_storage",
            "name",
            "storage",
            "virtual_machine",
            "vmid",
            "node",
            "subtype",
            "status",
            "snaptime",
            "parent",
            "description",
        )

        default_columns = (
            "pk",
            "proxmox_storage",
            "name",
            "storage",
            "virtual_machine",
            "vmid",
            "node",
            "subtype",
            "status",
            "snaptime",
            "parent",
        )
