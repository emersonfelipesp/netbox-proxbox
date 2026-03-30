"""Define NetBox table classes for endpoint list views."""

# Django Imports
import django_tables2 as tables
from django.utils.translation import gettext as _

# NetBox Imports
from netbox.tables import NetBoxTable, ChoiceFieldColumn
from netbox.tables.columns import BooleanColumn

# Proxbox Imports
from netbox_proxbox.models import (
    ProxmoxEndpoint,
    NetBoxEndpoint,
    FastAPIEndpoint,
)
from netbox_proxbox.tables.vm_backup import VMBackupTable
from netbox_proxbox.tables.vm_snapshot import VMSnapshotTable


class ProxmoxEndpointTable(NetBoxTable):
    """django-tables2 layout for Proxmox endpoint inventory."""

    name = tables.Column(linkify=True)
    ip_address = tables.Column(linkify=True)
    mode = ChoiceFieldColumn()
    verify_ssl = BooleanColumn()

    class Meta(NetBoxTable.Meta):
        model = ProxmoxEndpoint
        fields = (
            "pk",
            "id",
            "name",
            "domain",
            "ip_address",
            "port",
            "mode",
            "version",
            "repoid",
            "username",
            "token_name",
            "verify_ssl",
            "actions",
        )

        default_columns = (
            "pk",
            "name",
            "domain",
            "ip_address",
            "port",
            "mode",
            "version",
            "verify_ssl",
        )


class NetBoxEndpointTable(NetBoxTable):
    """django-tables2 layout for remote NetBox API endpoint inventory."""

    name = tables.Column(linkify=True)
    ip_address = tables.Column(linkify=True)
    verify_ssl = BooleanColumn()
    token = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = NetBoxEndpoint
        fields = (
            "pk",
            "id",
            "name",
            "ip_address",
            "port",
            "verify_ssl",
            "token",
            "actions",
        )

        default_columns = ("pk", "name", "ip_address", "port", "verify_ssl", "token")


class FastAPIEndpointTable(NetBoxTable):
    """django-tables2 layout for ProxBox FastAPI backend endpoint inventory."""

    name = tables.Column(linkify=True)
    ip_address = tables.Column(linkify=True)
    verify_ssl = BooleanColumn()

    class Meta(NetBoxTable.Meta):
        model = FastAPIEndpoint
        fields = (
            "pk",
            "id",
            "name",
            "domain",
            "ip_address",
            "port",
            "verify_ssl",
            "use_websocket",
            "websocket_domain",
            "websocket_port",
            "server_side_websocket",
            "token",
            "actions",
        )

        default_columns = (
            "pk",
            "name",
            "domain",
            "ip_address",
            "port",
            "verify_ssl",
            "use_websocket",
            "websocket_domain",
        )
