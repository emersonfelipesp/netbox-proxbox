"""Define the NetBox table used to render VM snapshot records."""

from django_tables2 import tables
from django.utils.translation import gettext as _

from netbox.tables import NetBoxTable, ChoiceFieldColumn

from netbox_proxbox.models import VMSnapshot


class VMSnapshotTable(NetBoxTable):
    """django-tables2 layout for VM snapshot list views."""

    virtual_machine = tables.Column(linkify=True)
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
            "name",
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
            "name",
            "virtual_machine",
            "vmid",
            "node",
            "subtype",
            "status",
            "snaptime",
            "parent",
        )
