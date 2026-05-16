"""django-tables2 layouts for netbox-pbs list views."""

from __future__ import annotations

import django_tables2 as tables
from netbox.tables import NetBoxTable
from netbox.tables.columns import BooleanColumn

from netbox_pbs.models import PBSDatastore, PBSJob, PBSServer, PBSSnapshot


class PBSServerTable(NetBoxTable):
    name = tables.Column(linkify=True)
    verify_ssl = BooleanColumn()

    class Meta(NetBoxTable.Meta):
        model = PBSServer
        fields = (
            "pk",
            "id",
            "name",
            "host",
            "port",
            "token_id",
            "verify_ssl",
            "status",
            "version",
            "last_seen_at",
            "actions",
        )
        default_columns = (
            "name",
            "host",
            "port",
            "verify_ssl",
            "status",
            "version",
            "last_seen_at",
        )


class PBSDatastoreTable(NetBoxTable):
    name = tables.Column(linkify=True)
    server = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = PBSDatastore
        fields = (
            "pk",
            "id",
            "name",
            "server",
            "path",
            "used_bytes",
            "total_bytes",
            "avail_bytes",
            "gc_status",
            "comment",
            "last_seen_at",
            "actions",
        )
        default_columns = (
            "name",
            "server",
            "path",
            "used_bytes",
            "total_bytes",
            "avail_bytes",
            "gc_status",
            "last_seen_at",
        )


class PBSSnapshotTable(NetBoxTable):
    backup_id = tables.Column(linkify=True)
    server = tables.Column(linkify=True)
    protected = BooleanColumn()

    class Meta(NetBoxTable.Meta):
        model = PBSSnapshot
        fields = (
            "pk",
            "id",
            "server",
            "datastore_name",
            "backup_type",
            "backup_id",
            "backup_time",
            "size_bytes",
            "owner",
            "protected",
            "verification_state",
            "last_seen_at",
            "actions",
        )
        default_columns = (
            "server",
            "datastore_name",
            "backup_type",
            "backup_id",
            "backup_time",
            "size_bytes",
            "protected",
            "verification_state",
        )


class PBSJobTable(NetBoxTable):
    job_id = tables.Column(linkify=True)
    server = tables.Column(linkify=True)
    disable = BooleanColumn()

    class Meta(NetBoxTable.Meta):
        model = PBSJob
        fields = (
            "pk",
            "id",
            "server",
            "job_type",
            "job_id",
            "store",
            "schedule",
            "disable",
            "last_run_state",
            "last_run_endtime",
            "next_run",
            "last_seen_at",
            "actions",
        )
        default_columns = (
            "server",
            "job_type",
            "job_id",
            "store",
            "schedule",
            "disable",
            "last_run_state",
            "next_run",
        )
