"""django-tables2 layouts for netbox-pbs list views.

The six tables here back the per-model list and tab views. PBSEndpoint
is the only writable model in v1; the other five are reflected from PBS
by the read-only sync that lands in PR C3, so their list views render
without add/edit/bulk-action controls (configured in ``views.py`` via
the ``actions`` dict on each ``ObjectListView``).
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from django_tables2 import tables

from netbox.tables import ChoiceFieldColumn, NetBoxTable

from netbox_pbs.models import (
    PBSBackupGroup,
    PBSDatastore,
    PBSEndpoint,
    PBSJobStatus,
    PBSNode,
    PBSSnapshot,
)


class PBSEndpointTable(NetBoxTable):
    """List columns for the writable PBS endpoint inventory."""

    name = tables.Column(linkify=True)
    host = tables.Column()
    port = tables.Column()
    verify_ssl = tables.BooleanColumn(verbose_name=_("Verify SSL"))
    last_seen_at = tables.DateTimeColumn(verbose_name=_("Last seen"))

    class Meta(NetBoxTable.Meta):
        model = PBSEndpoint
        fields = (
            "pk",
            "id",
            "name",
            "host",
            "port",
            "token_id",
            "fingerprint",
            "verify_ssl",
            "timeout",
            "last_seen_at",
        )
        default_columns = (
            "pk",
            "name",
            "host",
            "port",
            "verify_ssl",
            "last_seen_at",
        )


class PBSNodeTable(NetBoxTable):
    """List columns for read-only PBS node mirrors."""

    endpoint = tables.Column(linkify=True)
    hostname = tables.Column(linkify=True)
    version = tables.Column()
    uptime_seconds = tables.Column(verbose_name=_("Uptime (s)"))
    cpu_pct = tables.Column(verbose_name=_("CPU %"))
    last_seen_at = tables.DateTimeColumn(verbose_name=_("Last seen"))

    class Meta(NetBoxTable.Meta):
        model = PBSNode
        fields = (
            "pk",
            "id",
            "endpoint",
            "hostname",
            "version",
            "uptime_seconds",
            "cpu_pct",
            "memory_used",
            "memory_total",
            "last_seen_at",
        )
        default_columns = (
            "pk",
            "endpoint",
            "hostname",
            "version",
            "cpu_pct",
            "last_seen_at",
        )


class PBSDatastoreTable(NetBoxTable):
    """List columns for read-only PBS datastore mirrors."""

    endpoint = tables.Column(linkify=True)
    name = tables.Column(linkify=True)
    path = tables.Column()
    total_bytes = tables.Column(verbose_name=_("Total bytes"))
    used_bytes = tables.Column(verbose_name=_("Used bytes"))
    available_bytes = tables.Column(verbose_name=_("Available bytes"))
    gc_status = ChoiceFieldColumn(verbose_name=_("GC status"))
    last_gc_at = tables.DateTimeColumn(verbose_name=_("Last GC"))

    class Meta(NetBoxTable.Meta):
        model = PBSDatastore
        fields = (
            "pk",
            "id",
            "endpoint",
            "name",
            "path",
            "total_bytes",
            "used_bytes",
            "available_bytes",
            "gc_status",
            "last_gc_at",
        )
        default_columns = (
            "pk",
            "endpoint",
            "name",
            "used_bytes",
            "total_bytes",
            "gc_status",
            "last_gc_at",
        )


class PBSBackupGroupTable(NetBoxTable):
    """List columns for read-only PBS backup-group mirrors."""

    datastore = tables.Column(linkify=True)
    backup_type = ChoiceFieldColumn(verbose_name=_("Type"))
    backup_id = tables.Column(linkify=True, verbose_name=_("Backup ID"))
    owner = tables.Column()
    comment = tables.Column()

    class Meta(NetBoxTable.Meta):
        model = PBSBackupGroup
        fields = (
            "pk",
            "id",
            "datastore",
            "backup_type",
            "backup_id",
            "owner",
            "comment",
        )
        default_columns = (
            "pk",
            "datastore",
            "backup_type",
            "backup_id",
            "owner",
        )


class PBSSnapshotTable(NetBoxTable):
    """List columns for read-only PBS snapshot mirrors."""

    backup_group = tables.Column(linkify=True)
    backup_time = tables.DateTimeColumn(linkify=True, verbose_name=_("Backup time"))
    size_bytes = tables.Column(verbose_name=_("Size"))
    encrypted = tables.BooleanColumn()
    verified = ChoiceFieldColumn()
    protected = tables.BooleanColumn()

    class Meta(NetBoxTable.Meta):
        model = PBSSnapshot
        fields = (
            "pk",
            "id",
            "backup_group",
            "backup_time",
            "size_bytes",
            "encrypted",
            "verified",
            "protected",
            "comment",
        )
        default_columns = (
            "pk",
            "backup_group",
            "backup_time",
            "size_bytes",
            "encrypted",
            "verified",
            "protected",
        )


class PBSJobStatusTable(NetBoxTable):
    """List columns for read-only PBS scheduled-job mirrors."""

    endpoint = tables.Column(linkify=True)
    job_type = ChoiceFieldColumn(verbose_name=_("Type"))
    job_id = tables.Column(linkify=True, verbose_name=_("Job ID"))
    datastore = tables.Column(linkify=True)
    enabled = tables.BooleanColumn()
    last_run_at = tables.DateTimeColumn(verbose_name=_("Last run"))
    last_run_state = ChoiceFieldColumn(verbose_name=_("Last state"))
    next_run_at = tables.DateTimeColumn(verbose_name=_("Next run"))

    class Meta(NetBoxTable.Meta):
        model = PBSJobStatus
        fields = (
            "pk",
            "id",
            "endpoint",
            "job_type",
            "job_id",
            "datastore",
            "enabled",
            "last_run_at",
            "last_run_state",
            "last_run_duration_seconds",
            "next_run_at",
        )
        default_columns = (
            "pk",
            "endpoint",
            "job_type",
            "job_id",
            "datastore",
            "enabled",
            "last_run_at",
            "last_run_state",
        )
