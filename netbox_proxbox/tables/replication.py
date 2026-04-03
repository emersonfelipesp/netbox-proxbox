"""Define the NetBox table used to render Replication records."""

from django.utils.translation import gettext as _
from django_tables2 import tables
from netbox.tables import ChoiceFieldColumn, NetBoxTable
from netbox.tables.columns import BooleanColumn

from netbox_proxbox.models import Replication


class ReplicationTable(NetBoxTable):
    """django-tables2 layout for Replication list views."""

    replication_id = tables.Column(linkify=True)
    virtual_machine = tables.Column(linkify=True)
    proxmox_node = tables.Column(linkify=True)
    job_type = ChoiceFieldColumn(
        verbose_name=_("Type"),
    )
    disable = BooleanColumn(
        verbose_name=_("Disabled"),
    )
    remove_job = ChoiceFieldColumn(
        verbose_name=_("Remove Job"),
    )

    class Meta(NetBoxTable.Meta):
        model = Replication
        fields = (
            "pk",
            "id",
            "replication_id",
            "virtual_machine",
            "proxmox_node",
            "guest",
            "target",
            "job_type",
            "schedule",
            "rate",
            "disable",
            "source",
            "jobnum",
            "remove_job",
            "comment",
        )

        default_columns = (
            "pk",
            "replication_id",
            "virtual_machine",
            "target",
            "job_type",
            "schedule",
            "disable",
        )
