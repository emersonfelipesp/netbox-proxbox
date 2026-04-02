"""Tables for ProxmoxCluster and ProxmoxNode records."""

from django_tables2 import tables
from django.utils.translation import gettext as _

from netbox.tables import NetBoxTable
from netbox.tables.columns import BooleanColumn, ChoiceFieldColumn

from netbox_proxbox.models import ProxmoxCluster, ProxmoxNode


class ProxmoxClusterTable(NetBoxTable):
    """django-tables2 layout for Proxmox cluster list views."""

    endpoint = tables.Column(linkify=True)
    netbox_cluster = tables.Column(linkify=True, verbose_name=_("NetBox Cluster"))
    name = tables.Column(linkify=True)
    mode = ChoiceFieldColumn()
    quorate = BooleanColumn(verbose_name=_("Quorate"))

    class Meta(NetBoxTable.Meta):
        model = ProxmoxCluster
        fields = (
            "pk",
            "id",
            "endpoint",
            "netbox_cluster",
            "name",
            "cluster_id",
            "mode",
            "nodes_count",
            "quorate",
            "version",
            "created",
            "last_updated",
        )
        default_columns = (
            "pk",
            "endpoint",
            "name",
            "mode",
            "nodes_count",
            "quorate",
            "netbox_cluster",
        )


class ProxmoxNodeTable(NetBoxTable):
    """django-tables2 layout for Proxmox node list views."""

    endpoint = tables.Column(linkify=True)
    proxmox_cluster = tables.Column(linkify=True, verbose_name=_("Cluster"))
    netbox_device = tables.Column(linkify=True, verbose_name=_("NetBox Device"))
    name = tables.Column(linkify=True)
    online = BooleanColumn(verbose_name=_("Online"))
    local = BooleanColumn(verbose_name=_("Local"))
    cpu_usage = tables.Column(verbose_name=_("CPU %"))
    memory_usage_gb = tables.Column(
        accessor="memory_usage",
        verbose_name=_("Memory (GB)"),
        orderable=True,
    )

    class Meta(NetBoxTable.Meta):
        model = ProxmoxNode
        fields = (
            "pk",
            "id",
            "endpoint",
            "proxmox_cluster",
            "netbox_device",
            "name",
            "node_id",
            "ip_address",
            "online",
            "local",
            "cpu_usage",
            "max_cpu",
            "memory_usage",
            "memory_usage_gb",
            "max_memory",
            "support_level",
            "created",
            "last_updated",
        )
        default_columns = (
            "pk",
            "name",
            "ip_address",
            "online",
            "cpu_usage",
            "memory_usage_gb",
            "proxmox_cluster",
            "netbox_device",
        )

    def render_cpu_usage(self, value):
        """Format CPU usage as percentage."""
        if value is not None:
            return f"{value:.1f}%"
        return "—"

    def render_memory_usage_gb(self, record):
        """Convert memory bytes to GB for display."""
        if record.memory_usage is not None:
            gb = record.memory_usage / (1024**3)
            if record.max_memory:
                max_gb = record.max_memory / (1024**3)
                return f"{gb:.1f} / {max_gb:.1f} GB"
            return f"{gb:.1f} GB"
        return "—"
