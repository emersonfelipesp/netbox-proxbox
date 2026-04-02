"""Define the NetBox table used to render backup routine records."""

from django_tables2 import tables
from django.utils.translation import gettext as _

from netbox.tables import NetBoxTable, ChoiceFieldColumn
from netbox.tables.columns import BooleanColumn

from netbox_proxbox.models import BackupRoutine


class BackupRoutineTable(NetBoxTable):
    """django-tables2 layout for backup routine list views."""

    job_id = tables.Column(
        verbose_name=_("Job ID"),
    )
    enabled = BooleanColumn(
        verbose_name=_("Enabled"),
    )
    node = tables.Column(
        linkify=True,
        verbose_name=_("Node"),
    )
    schedule = tables.Column(
        verbose_name=_("Schedule"),
    )
    next_run = tables.Column(
        verbose_name=_("Next Run"),
    )
    storage = tables.Column(
        linkify=True,
        verbose_name=_("Storage"),
    )
    status = ChoiceFieldColumn(
        verbose_name=_("Status"),
    )
    keep_last = tables.Column(
        verbose_name=_("Keep Last"),
    )
    keep_daily = tables.Column(
        verbose_name=_("Keep Daily"),
    )

    class Meta(NetBoxTable.Meta):
        model = BackupRoutine
        fields = (
            "pk",
            "id",
            "job_id",
            "enabled",
            "node",
            "schedule",
            "next_run",
            "storage",
            "status",
            "keep_last",
            "keep_daily",
        )

        default_columns = (
            "pk",
            "job_id",
            "enabled",
            "node",
            "schedule",
            "next_run",
            "storage",
            "status",
        )
