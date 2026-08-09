"""Tables for Proxmox metrics integration metadata."""

from __future__ import annotations

import django_tables2 as tables
from netbox.tables import NetBoxTable
from netbox.tables.columns import BooleanColumn

from netbox_proxbox.models import ProxmoxMetricsInfluxDB


class ProxmoxMetricsInfluxDBTable(NetBoxTable):
    """django-tables2 layout for Proxmox InfluxDB metrics endpoint mappings."""

    name = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)
    proxmox_cluster = tables.Column(linkify=True)
    verify_tls = BooleanColumn()
    enabled = BooleanColumn()

    def render_influx_url(self, record) -> str:
        """Render only a credential-free InfluxDB base URL; mask anything else."""
        return record.influx_url_display

    def value_influx_url(self, record) -> str:
        """Export the same fail-closed value the list page renders."""
        return record.influx_url_display

    class Meta(NetBoxTable.Meta):
        model = ProxmoxMetricsInfluxDB
        fields = (
            "pk",
            "id",
            "name",
            "endpoint",
            "proxmox_cluster",
            "influx_url",
            "org",
            "bucket",
            "measurement_prefix",
            "verify_tls",
            "enabled",
            "created",
            "last_updated",
        )
        default_columns = (
            "pk",
            "name",
            "endpoint",
            "proxmox_cluster",
            "influx_url",
            "org",
            "bucket",
            "verify_tls",
            "enabled",
        )
