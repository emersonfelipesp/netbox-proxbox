"""Define NetBox table classes for endpoint list views."""

# Django Imports
import django_tables2 as tables
from django.utils.html import format_html
from django.utils.translation import gettext as _

# NetBox Imports
from netbox.tables import ChoiceFieldColumn, NetBoxTable
from netbox.tables.columns import BooleanColumn

# Proxbox Imports
from netbox_proxbox.models import (
    FastAPIEndpoint,
    NetBoxEndpoint,
    ProxmoxEndpoint,
)
from netbox_proxbox.tables.backup_routine import BackupRoutineTable
from netbox_proxbox.tables.cluster import ProxmoxClusterTable, ProxmoxNodeTable
from netbox_proxbox.tables.replication import ReplicationTable
from netbox_proxbox.tables.storage import ProxmoxStorageTable
from netbox_proxbox.tables.vm_backup import VMBackupTable
from netbox_proxbox.tables.vm_snapshot import VMSnapshotTable
from netbox_proxbox.tables.vm_task_history import VMTaskHistoryTable

STATUS_BADGE_TEMPLATE = """
<span class="badge text-bg-grey"
      data-service-status-url="{% url 'plugins:netbox_proxbox:keepalive_status' '{{ service }}' record.pk %}">
    <span class="spinner-border spinner-border-sm" role="status"></span>
</span>
"""


class ProxmoxEndpointTable(NetBoxTable):
    """django-tables2 layout for Proxmox endpoint inventory."""

    name = tables.Column(linkify=True)
    ip_address = tables.Column(linkify=True)
    site = tables.Column(linkify=True)
    tenant = tables.Column(linkify=True)
    mode = ChoiceFieldColumn()
    verify_ssl = BooleanColumn()
    status = tables.TemplateColumn(
        template_code=STATUS_BADGE_TEMPLATE.replace("{{ service }}", "proxmox"),
        verbose_name=_("Status"),
        orderable=False,
    )

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
            "timeout",
            "max_retries",
            "retry_backoff",
            "site",
            "tenant",
            "status",
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
            "status",
            "verify_ssl",
        )


class NetBoxEndpointTable(NetBoxTable):
    """django-tables2 layout for remote NetBox API endpoint inventory."""

    name = tables.Column(linkify=True)
    ip_address = tables.Column(linkify=True)
    verify_ssl = BooleanColumn()
    token = tables.Column(linkify=True)
    status = tables.TemplateColumn(
        template_code=STATUS_BADGE_TEMPLATE.replace("{{ service }}", "netbox"),
        verbose_name=_("Status"),
        orderable=False,
    )

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
            "status",
            "actions",
        )

        default_columns = (
            "pk",
            "name",
            "ip_address",
            "port",
            "status",
            "verify_ssl",
            "token",
        )


class FastAPIEndpointTable(NetBoxTable):
    """django-tables2 layout for ProxBox FastAPI backend endpoint inventory."""

    name = tables.Column(linkify=True)
    ip_address = tables.Column(linkify=True)
    use_https = BooleanColumn()
    verify_ssl = BooleanColumn()
    status = tables.TemplateColumn(
        template_code=STATUS_BADGE_TEMPLATE.replace("{{ service }}", "fastapi"),
        verbose_name=_("Status"),
        orderable=False,
    )

    class Meta(NetBoxTable.Meta):
        model = FastAPIEndpoint
        fields = (
            "pk",
            "id",
            "name",
            "domain",
            "ip_address",
            "port",
            "use_https",
            "verify_ssl",
            "use_websocket",
            "websocket_domain",
            "websocket_port",
            "server_side_websocket",
            "token",
            "status",
            "actions",
        )

        default_columns = (
            "pk",
            "name",
            "domain",
            "ip_address",
            "port",
            "status",
            "use_https",
            "verify_ssl",
            "use_websocket",
            "websocket_domain",
        )
