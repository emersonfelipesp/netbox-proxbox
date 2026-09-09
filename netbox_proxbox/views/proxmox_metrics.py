"""NetBox CRUD views for Proxmox metrics integration metadata."""

from __future__ import annotations

from django.http import HttpRequest
from netbox.object_actions import AddObject, BulkExport, BulkDelete
from netbox.views import generic
from utilities.views import register_model_view

from netbox_proxbox.filtersets import ProxmoxMetricsInfluxDBFilterSet
from netbox_proxbox.forms import (
    ProxmoxMetricsInfluxDBFilterForm,
    ProxmoxMetricsInfluxDBForm,
    ProxmoxMetricsInfluxDBQueryForm,
)
from netbox_proxbox.models import ProxmoxMetricsInfluxDB
from netbox_proxbox.services.metrics_influx import MetricsProxyError, query_metrics
from netbox_proxbox.tables import ProxmoxMetricsInfluxDBTable


__all__ = (
    "ProxmoxMetricsInfluxDBView",
    "ProxmoxMetricsInfluxDBListView",
    "ProxmoxMetricsInfluxDBEditView",
    "ProxmoxMetricsInfluxDBDeleteView",
    "ProxmoxMetricsInfluxDBBulkDeleteView",
    "ProxmoxMetricsInfluxDBDataView",
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
    actions = (AddObject, BulkExport, BulkDelete)


@register_model_view(ProxmoxMetricsInfluxDB)
class ProxmoxMetricsInfluxDBView(generic.ObjectView):
    """Detail view for one Proxmox cluster InfluxDB metrics endpoint mapping."""

    queryset = _METRICS_INFLUXDB_QUERYSET


@register_model_view(ProxmoxMetricsInfluxDB, "data", path="data")
class ProxmoxMetricsInfluxDBDataView(generic.ObjectView):
    """Retrieve live metrics through proxbox-api for one mapping."""

    queryset = _METRICS_INFLUXDB_QUERYSET
    template_name = "netbox_proxbox/proxmoxmetricsinfluxdb_data.html"

    def get_extra_context(
        self, request: HttpRequest, instance: ProxmoxMetricsInfluxDB
    ) -> dict[str, object]:
        form = ProxmoxMetricsInfluxDBQueryForm(request.GET or None)
        context: dict[str, object] = {
            "form": form,
            "metrics": None,
            "detail": None,
        }
        if not request.GET:
            return context
        if not form.is_valid():
            context["detail"] = "Correct the metric query filters and try again."
            return context
        try:
            context["metrics"] = query_metrics(instance, form.cleaned_data)
        except MetricsProxyError as exc:
            context["detail"] = str(exc)
        return context


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
