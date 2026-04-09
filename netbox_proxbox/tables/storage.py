"""Table for Proxmox storage records."""

from django_tables2 import tables
from django.utils.translation import gettext as _

from netbox.tables import NetBoxTable
from netbox.tables.columns import BooleanColumn

from netbox_proxbox.models import ProxmoxStorage


class ProxmoxStorageTable(NetBoxTable):
    """django-tables2 layout for Proxmox storage list views."""

    cluster = tables.Column(linkify=True)
    name = tables.Column(linkify=True)
    shared = BooleanColumn(verbose_name=_("Shared"))
    enabled = BooleanColumn(verbose_name=_("Enabled"))

    class Meta(NetBoxTable.Meta):
        model = ProxmoxStorage
        fields = (
            "pk",
            "id",
            "cluster",
            "name",
            "storage_type",
            "content",
            "path",
            "nodes",
            "shared",
            "enabled",
            "server",
            "port",
            "pool",
            "datastore",
            "format",
        )
        default_columns = (
            "pk",
            "cluster",
            "name",
            "storage_type",
            "content",
            "path",
            "server",
            "shared",
            "enabled",
        )
