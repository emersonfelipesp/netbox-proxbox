"""Implement the plugin dashboard pages and re-export major view entrypoints."""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View
from netbox import configuration
from utilities.views import (
    ConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
)
from virtualization.models import VirtualMachine, VMInterface

from netbox_proxbox import github
from netbox_proxbox.models import FastAPIEndpoint, NetBoxEndpoint, ProxmoxEndpoint
from netbox_proxbox.utils import get_fastapi_url
from netbox_proxbox.views.home_context import build_home_dashboard_context
from netbox_proxbox.views.job_stream import JobStreamSSEView
from netbox_proxbox.views.proxbox_access import (
    RequireProxboxDashboardAccessMixin,
    permission_view_fastapi_endpoint,
)

from .backup_routine import (
    BackupRoutineBulkDeleteView,
    BackupRoutineDeleteView,
    BackupRoutineEditView,
    BackupRoutineListView,
    BackupRoutineView,
)
from .cards import get_proxmox_card
from .cluster import (
    ClusterStoragesTabView,
    ClusterSummaryTabView,
)
from .cluster_nodes_tab import ProxmoxEndpointClusterNodesTabView
from .dashboard import DashboardView
from .endpoints import (
    FastAPIEndpointDeleteView,
    FastAPIEndpointEditView,
    FastAPIEndpointListView,
    FastAPIEndpointView,
    NetBoxEndpointDeleteView,
    NetBoxEndpointEditView,
    NetBoxEndpointListView,
    NetBoxEndpointView,
    ProxmoxEndpointDeleteView,
    ProxmoxEndpointEditView,
    ProxmoxEndpointListView,
    ProxmoxEndpointView,
)
from .external_pages import discord_redirect, discussions_redirect, telegram_redirect
from .keepalive_status import get_service_status
from .logs import BackendLogPathUpdateView, BackendLogsView
from .replication import (
    ReplicationBulkDeleteView,
    ReplicationBulkEditView,
    ReplicationBulkImportView,
    ReplicationDeleteView,
    ReplicationEditView,
    ReplicationListView,
    ReplicationTabView,
    ReplicationView,
)
from .resource_list_views import (
    InterfacesView as _InterfacesView,
    IPAddressesView as _IPAddressesView,
    LXCContainersView as _LXCContainersView,
    NodesView as _NodesView,
    VirtualMachinesView as _VirtualMachinesView,
)
from .schedule_sync import QuickScheduleSyncFromHomeView, ScheduleSyncView
from .settings import SettingsView
from .storage import (
    ProxmoxStorageBulkDeleteView,
    ProxmoxStorageDeleteView,
    ProxmoxStorageEditView,
    ProxmoxStorageListView,
    ProxmoxStorageView,
)
from .sync import (
    sync_backup_routines,
    sync_devices,
    sync_full_update,
    sync_ip_addresses,
    sync_network_interfaces,
    sync_replications,
    sync_selected_storage,
    sync_selected_virtual_machines,
    sync_selected_vm_backups,
    sync_selected_vm_snapshots,
    sync_selected_vm_task_history,
    sync_storage,
    sync_virtual_disks,
    sync_virtual_machines,
    sync_vm_backups,
    sync_vm_snapshots,
)
from .vm_backup import (
    VMBackupBulkDeleteView,
    VMBackupDeleteView,
    VMBackupEditView,
    VMBackupListView,
    VMBackupTabView,
    VMBackupView,
)

# Task History tab and detail views live in ``vm_task_history``.
from .vm_config import ProxmoxVMConfigTabView
from .vm_snapshot import (
    VMSnapshotBulkDeleteView,
    VMSnapshotBulkEditView,
    VMSnapshotBulkImportView,
    VMSnapshotDeleteView,
    VMSnapshotEditView,
    VMSnapshotListView,
    VMSnapshotTabView,
    VMSnapshotView,
)
from .vm_sync_now import VirtualMachineSyncNowView
from .vm_task_history import (
    VMTaskHistoryBulkDeleteView,
    VMTaskHistoryDeleteView,
    VMTaskHistoryEditView,
    VMTaskHistoryListView,
    VMTaskHistoryTabView,
    VMTaskHistoryView,
)


class HomeView(
    ConditionalLoginRequiredMixin,
    RequireProxboxDashboardAccessMixin,
    View,
):
    """Plugin dashboard with endpoint lists and example FastAPI URLs for the UI."""

    template_name = "netbox_proxbox/home.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        """Render home with visible endpoint rows and resolved FastAPI HTTP/WebSocket URLs."""
        return render(
            request,
            self.template_name,
            build_home_dashboard_context(request),
        )


class TestWebSocketView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """Developer page to exercise backend WebSocket connectivity from the browser."""

    template_name = "netbox_proxbox/test/websocket.html"

    def get_required_permission(self) -> str:
        """Require ``view`` on ``FastAPIEndpoint``."""
        return permission_view_fastapi_endpoint()

    def get(self, request: HttpRequest) -> HttpResponse:
        """Render the test template with HTTP and WS base URLs from the first endpoint."""
        fastapi_object = FastAPIEndpoint.objects.restrict(request.user, "view").first()
        if fastapi_object is None:
            return render(request, self.template_name, {})

        fastapi_ip = str(fastapi_object.ip_address).split("/")[0]
        fastapi_url = (
            f"https://{fastapi_ip}:{fastapi_object.port}"
            if fastapi_object.verify_ssl
            else f"http://{fastapi_ip}:{fastapi_object.port}"
        )
        fastapi_websocket_url = (
            f"wss://{fastapi_ip}:{fastapi_object.port}"
            if fastapi_object.verify_ssl
            else f"ws://{fastapi_ip}:{fastapi_object.port}"
        )

        return render(
            request,
            self.template_name,
            {
                "fastapi_url": fastapi_url,
                "fastapi_websocket_url": fastapi_websocket_url,
            },
        )


class ContributingView(ConditionalLoginRequiredMixin, View):
    """Render CONTRIBUTING.md from GitHub for in-app contributor guidance."""

    template_name = "netbox_proxbox/contributing.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        """Fetch markdown from ``github.get`` and pass HTML to the template."""
        return render(
            request,
            self.template_name,
            {
                "html": github.get(filename="CONTRIBUTING.md"),
                "title": "Contributing to Proxbox Project",
            },
        )


class CommunityView(ConditionalLoginRequiredMixin, View):
    """Static community landing page for the plugin."""

    template_name = "netbox_proxbox/community.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        """Render the community template with a page title."""
        return render(request, self.template_name, {"title": "Join our Community!"})


class NodesView(_NodesView):
    """Compatibility wrapper for resource list views kept in this module surface."""


class VirtualMachinesView(_VirtualMachinesView):
    """Compatibility wrapper for resource list views kept in this module surface."""


class LXCContainersView(_LXCContainersView):
    """Compatibility wrapper for resource list views kept in this module surface."""


class InterfacesView(_InterfacesView):
    """Compatibility wrapper for resource list views kept in this module surface."""


# IP address list queries still prefetch_related("assigned_object") in the extracted module.
class IPAddressesView(_IPAddressesView):
    """Compatibility wrapper for resource list views kept in this module surface."""
