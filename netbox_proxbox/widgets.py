"""Dashboard widgets for the NetBox home page.

Registered via ``@register_widget`` and imported in ``PluginConfig.ready()``.
Each widget performs DB-only reads — no synchronous HTTP calls in ``render()``.
"""

from __future__ import annotations

from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _
from extras.dashboard.utils import register_widget
from extras.dashboard.widgets import DashboardWidget

from netbox_proxbox.models import (
    BackupRoutine,
    FastAPIEndpoint,
    NetBoxEndpoint,
    ProxmoxCluster,
    ProxmoxEndpoint,
    ProxmoxNode,
    ProxmoxStorage,
    Replication,
    VMBackup,
    VMSnapshot,
    VMTaskHistory,
)


def _safe_count(model, request):
    """Return the count for a model, respecting object-level permissions."""
    try:
        return model.objects.restrict(request.user, "view").count()
    except AttributeError:
        return model.objects.count()


@register_widget
class ProxboxSyncStatusWidget(DashboardWidget):
    default_title = _("Proxbox Sync Status")
    description = _("Last Proxbox sync job status and synced object summary.")
    width = 6
    height = 4

    def render(self, request):
        from core.choices import JobStatusChoices
        from core.models import Job

        from netbox_proxbox.jobs import is_proxbox_sync_job

        latest_job = None
        active_job = None
        for job in Job.objects.restrict(request.user, "view").order_by("-created")[:50]:
            if not is_proxbox_sync_job(job):
                continue
            if latest_job is None:
                latest_job = job
            if active_job is None and job.status in JobStatusChoices.ENQUEUED_STATE_CHOICES:
                active_job = job
            if latest_job and active_job:
                break

        counts = {
            "clusters": _safe_count(ProxmoxCluster, request),
            "nodes": _safe_count(ProxmoxNode, request),
            "endpoints": _safe_count(ProxmoxEndpoint, request),
            "storage": _safe_count(ProxmoxStorage, request),
            "backups": _safe_count(VMBackup, request),
            "snapshots": _safe_count(VMSnapshot, request),
        }

        return render_to_string(
            "netbox_proxbox/dashboard_widgets/sync_status.html",
            {
                "latest_job": latest_job,
                "active_job": active_job,
                "counts": counts,
            },
        )


@register_widget
class ProxboxObjectCountsWidget(DashboardWidget):
    default_title = _("Proxbox Object Counts")
    description = _("Counts of all Proxbox plugin model objects.")
    width = 4
    height = 4

    def render(self, request):
        from django.urls import NoReverseMatch, reverse

        items = [
            ("Proxmox Endpoints", ProxmoxEndpoint, "plugins:netbox_proxbox:proxmoxendpoint_list"),
            ("Clusters", ProxmoxCluster, "plugins:netbox_proxbox:proxmoxcluster_list"),
            ("Nodes", ProxmoxNode, "plugins:netbox_proxbox:proxmoxnode_list"),
            ("Storage", ProxmoxStorage, "plugins:netbox_proxbox:proxmoxstorage_list"),
            ("VM Backups", VMBackup, "plugins:netbox_proxbox:vmbackup_list"),
            ("VM Snapshots", VMSnapshot, "plugins:netbox_proxbox:vmsnapshot_list"),
            ("Backup Routines", BackupRoutine, "plugins:netbox_proxbox:backuproutine_list"),
            ("Replications", Replication, "plugins:netbox_proxbox:replication_list"),
            ("Task History", VMTaskHistory, "plugins:netbox_proxbox:vmtaskhistory_list"),
        ]

        rows = []
        for label, model, url_name in items:
            count = _safe_count(model, request)
            try:
                url = reverse(url_name)
            except NoReverseMatch:
                url = None
            rows.append({"label": label, "count": count, "url": url})

        return render_to_string(
            "netbox_proxbox/dashboard_widgets/object_counts.html",
            {"rows": rows},
        )


@register_widget
class ProxboxEndpointStatusWidget(DashboardWidget):
    default_title = _("Proxbox Endpoints")
    description = _("Overview of configured Proxmox, NetBox, and FastAPI endpoints.")
    width = 6
    height = 3

    def render(self, request):
        from netbox_proxbox.views.dashboard_data import get_endpoint_display_ip

        proxmox_endpoints = []
        try:
            qs = ProxmoxEndpoint.objects.restrict(request.user, "view")
        except AttributeError:
            qs = ProxmoxEndpoint.objects.all()
        for ep in qs:
            proxmox_endpoints.append({
                "name": str(ep),
                "ip": get_endpoint_display_ip(ep),
                "mode": getattr(ep, "mode", "—"),
            })

        netbox_ep = None
        try:
            netbox_ep = NetBoxEndpoint.objects.first()
        except Exception:
            pass

        fastapi_ep = None
        try:
            fastapi_ep = FastAPIEndpoint.objects.first()
        except Exception:
            pass

        return render_to_string(
            "netbox_proxbox/dashboard_widgets/endpoint_status.html",
            {
                "proxmox_endpoints": proxmox_endpoints,
                "netbox_endpoint": netbox_ep,
                "fastapi_endpoint": fastapi_ep,
            },
        )
