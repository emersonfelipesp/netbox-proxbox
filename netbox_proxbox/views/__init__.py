"""Implement the plugin dashboard pages and re-export major view entrypoints."""

from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import render
from django.views import View

from netbox import configuration

from netbox_proxbox import github
from netbox_proxbox.models import FastAPIEndpoint, NetBoxEndpoint, ProxmoxEndpoint
from netbox_proxbox.utils import get_fastapi_url
from netbox_proxbox.views.home_context import build_home_dashboard_context
from netbox_proxbox.views.proxbox_access import (
    permission_view_fastapi_endpoint,
    user_may_access_proxbox_dashboard,
)
from utilities.views import (
    ConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
)

from .cards import get_proxmox_card
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
from .external_pages import DiscordView, DiscussionsView, TelegramView
from .keepalive_status import get_service_status
from .schedule_sync import QuickScheduleSyncFromHomeView, ScheduleSyncView
from .settings import SettingsView
from .sync import (
    sync_devices,
    sync_full_update,
    sync_virtual_machines,
    sync_virtual_disks,
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
from .vm_snapshot import (
    VMSnapshotBulkDeleteView,
    VMSnapshotDeleteView,
    VMSnapshotEditView,
    VMSnapshotListView,
    VMSnapshotTabView,
    VMSnapshotView,
)
from .vm_sync_now import VirtualMachineSyncNowView


class RequireProxboxDashboardEndpointViewMixin(AccessMixin):
    """Require view permission on at least one plugin endpoint model when logged in."""

    def dispatch(self, request, *args, **kwargs):
        """Block authenticated users who cannot see any ProxBox endpoint inventory."""
        if request.user.is_authenticated and not user_may_access_proxbox_dashboard(
            request.user
        ):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


class HomeView(
    ConditionalLoginRequiredMixin,
    RequireProxboxDashboardEndpointViewMixin,
    View,
):
    """Plugin dashboard with endpoint lists and example FastAPI URLs for the UI."""

    template_name = "netbox_proxbox/home.html"

    def get(self, request):
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

    def get_required_permission(self):
        """Require ``view`` on ``FastAPIEndpoint``."""
        return permission_view_fastapi_endpoint()

    def get(self, request):
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


class NodesView(ConditionalLoginRequiredMixin, View):
    """List NetBox devices tagged ``proxbox`` (synced nodes) for operational review."""

    template = "netbox_proxbox/devices.html"

    def get(self, request):
        """Load tagged devices and FastAPI URL hints for the devices template."""
        from dcim.models import Device
        from django.contrib.contenttypes.models import ContentType
        from extras.models import Tag, TaggedItem

        from netbox_proxbox.models import FastAPIEndpoint

        plugin_configuration = getattr(configuration, "PLUGINS_CONFIG", {})
        fastapi_endpoint = FastAPIEndpoint.objects.restrict(
            request.user, "view"
        ).first()
        fastapi_info = {}
        if fastapi_endpoint:
            fastapi_info = get_fastapi_url(fastapi_endpoint) or {}

        proxbox_tag = Tag.objects.filter(slug="proxbox").first()
        devices = []
        if proxbox_tag:
            device_content_type = ContentType.objects.get_for_model(Device)
            tagged_device_ids = list(
                TaggedItem.objects.filter(
                    tag=proxbox_tag, content_type=device_content_type
                ).values_list("object_id", flat=True)[:100]
            )
            if tagged_device_ids:
                devices = list(
                    Device.objects.restrict(request.user, "view")
                    .filter(id__in=tagged_device_ids)
                    .select_related(
                        "device_type__manufacturer", "role", "site", "tenant", "cluster"
                    )
                    .prefetch_related("interfaces__ip_addresses")
                )

        return render(
            request,
            self.template,
            {
                "configuration": plugin_configuration,
                "fastapi_url": fastapi_info.get("http_url", ""),
                "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                "devices": devices,
            },
        )


class VirtualMachinesView(ConditionalLoginRequiredMixin, View):
    """List VMs tagged ``proxbox`` for quick visibility alongside backend URLs."""

    template = "netbox_proxbox/virtual_machines.html"

    def get(self, request):
        """Load tagged VMs and FastAPI URL hints for the virtual machines template."""
        from django.contrib.contenttypes.models import ContentType
        from extras.models import Tag, TaggedItem
        from virtualization.models import VirtualMachine

        from netbox_proxbox.models import FastAPIEndpoint

        plugin_configuration = getattr(configuration, "PLUGINS_CONFIG", {})
        fastapi_endpoint = FastAPIEndpoint.objects.restrict(
            request.user, "view"
        ).first()
        fastapi_info = {}
        if fastapi_endpoint:
            fastapi_info = get_fastapi_url(fastapi_endpoint) or {}

        proxbox_tag = Tag.objects.filter(slug="proxbox").first()
        virtual_machines = []
        if proxbox_tag:
            vm_content_type = ContentType.objects.get_for_model(VirtualMachine)
            tagged_vm_ids = list(
                TaggedItem.objects.filter(
                    tag=proxbox_tag, content_type=vm_content_type
                ).values_list("object_id", flat=True)[:100]
            )
            if tagged_vm_ids:
                virtual_machines = list(
                    VirtualMachine.objects.restrict(request.user, "view")
                    .filter(id__in=tagged_vm_ids)
                    .select_related("site", "cluster", "role", "tenant", "platform")
                    .prefetch_related("interfaces__ip_addresses")
                )

        return render(
            request,
            self.template,
            {
                "configuration": plugin_configuration,
                "fastapi_url": fastapi_info.get("http_url", ""),
                "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                "virtual_machines": virtual_machines,
            },
        )


class ContributingView(ConditionalLoginRequiredMixin, View):
    """Render CONTRIBUTING.md from GitHub for in-app contributor guidance."""

    template_name = "netbox_proxbox/contributing.html"

    def get(self, request):
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

    def get(self, request):
        """Render the community template with a page title."""
        return render(request, self.template_name, {"title": "Join our Community!"})
