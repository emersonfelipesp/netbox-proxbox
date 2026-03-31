"""Define the NetBox table used to render VM task history records."""

from django_tables2 import tables
from django.utils.translation import gettext as _

from netbox.tables import NetBoxTable

from netbox_proxbox.models import VMTaskHistory


class VMTaskHistoryTable(NetBoxTable):
    """django-tables2 layout for VM task history list and tab views."""

    virtual_machine = tables.Column(linkify=True)
    description = tables.Column(linkify=True)
    start_time = tables.Column(
        verbose_name=_("Start Time"),
    )
    end_time = tables.Column(
        verbose_name=_("End Time"),
    )

    class Meta(NetBoxTable.Meta):
        model = VMTaskHistory
        fields = (
            "pk",
            "id",
            "virtual_machine",
            "vm_type",
            "upid",
            "node",
            "pid",
            "pstart",
            "task_id",
            "task_type",
            "username",
            "start_time",
            "end_time",
            "description",
            "status",
            "task_state",
            "exitstatus",
        )

        default_columns = (
            "pk",
            "start_time",
            "end_time",
            "username",
            "description",
            "status",
            "node",
            "task_type",
        )
