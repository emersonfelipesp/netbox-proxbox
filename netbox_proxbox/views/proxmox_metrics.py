"""NetBox CRUD views for Proxmox metrics integration metadata."""

from __future__ import annotations

from netbox.views import generic
from utilities.views import register_model_view

from netbox_proxbox.filtersets import ProxmoxMetricsInfluxDBFilterSet
from netbox_proxbox.forms import (
    ProxmoxMetricsInfluxDBFilterForm,
    ProxmoxMetricsInfluxDBForm,
)
from netbox_proxbox.models import ProxmoxMetricsInfluxDB
from netbox_proxbox.tables import ProxmoxMetricsInfluxDBTable


__all__ = (
    "ProxmoxMetricsInfluxDBView",
    "ProxmoxMetricsInfluxDBListView",
    "ProxmoxMetricsInfluxDBEditView",
    "ProxmoxMetricsInfluxDBDeleteView",
    "ProxmoxMetricsInfluxDBBulkDeleteView",
)


_METRICS_INFLUXDB_QUERYSET = ProxmoxMetricsInfluxDB.objects.select_related(
    "endpoint",
    "proxmox_cluster",
).prefetch_related("tags")


@register_model_view(ProxmoxMetricsInfluxDB, "list", path="", detail=False)
class ProxmoxMetricsInfluxDBListView(generic.ObjectListView):
    """Global list of Proxmox cluster InfluxDB metrics endpoint mappings."""

    queryset = _METRICS_INFLUXDB_QUERYSET
    table = ProxmoxMetricsInfluxDBTable
    filterset = ProxmoxMetricsInfluxDBFilterSet
    filterset_form = ProxmoxMetricsInfluxDBFilterForm
    actions = {
        "add": {"add"},
        "bulk_delete": {"delete"},
        "export": {"view"},
    }


@register_model_view(ProxmoxMetricsInfluxDB)
class ProxmoxMetricsInfluxDBView(generic.ObjectView):
    """Detail view for one Proxmox cluster InfluxDB metrics endpoint mapping."""

    queryset = _METRICS_INFLUXDB_QUERYSET


@register_model_view(ProxmoxMetricsInfluxDB, "add", detail=False)
@register_model_view(ProxmoxMetricsInfluxDB, "edit")
class ProxmoxMetricsInfluxDBEditView(generic.ObjectEditView):
    """Create or edit Proxmox cluster InfluxDB metrics endpoint metadata."""

    queryset = _METRICS_INFLUXDB_QUERYSET
    form = ProxmoxMetricsInfluxDBForm
    default_return_url = "plugins:netbox_proxbox:proxmoxmetricsinfluxdb_list"


@register_model_view(ProxmoxMetricsInfluxDB, "delete")
class ProxmoxMetricsInfluxDBDeleteView(generic.ObjectDeleteView):
    """Delete a Proxmox cluster InfluxDB metrics endpoint mapping."""

    queryset = _METRICS_INFLUXDB_QUERYSET
    default_return_url = "plugins:netbox_proxbox:proxmoxmetricsinfluxdb_list"


@register_model_view(ProxmoxMetricsInfluxDB, "bulk_delete", detail=False)
class ProxmoxMetricsInfluxDBBulkDeleteView(generic.BulkDeleteView):
    """Bulk-delete Proxmox cluster InfluxDB metrics endpoint mappings."""

    queryset = _METRICS_INFLUXDB_QUERYSET
    filterset = ProxmoxMetricsInfluxDBFilterSet
    table = ProxmoxMetricsInfluxDBTable
    default_return_url = "plugins:netbox_proxbox:proxmoxmetricsinfluxdb_list"
