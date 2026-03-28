from django.shortcuts import render
from django.views import View

from netbox import configuration

from netbox_proxbox import ProxboxConfig, github
from netbox_proxbox.models import FastAPIEndpoint, NetBoxEndpoint, ProxmoxEndpoint
from netbox_proxbox.utils import get_fastapi_url

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
from .sync import sync_devices, sync_full_update, sync_virtual_machines, sync_vm_backups
from .sync_process import (
    SyncProcessDeleteView,
    SyncProcessEditView,
    SyncProcessListView,
    SyncProcessView,
)
from .vm_backup import (
    VMBackupBulkDeleteView,
    VMBackupDeleteView,
    VMBackupEditView,
    VMBackupListView,
    VMBackupTabView,
    VMBackupView,
)


class HomeView(View):
    template_name = "netbox_proxbox/home.html"

    def get(self, request):
        default_config = getattr(ProxboxConfig, "default_settings", {})
        fastapi_example_url = "https://example.fastapi.com"
        fastapi_example_websocket_url = "wss://example.fastapi.com/ws"

        proxmox_endpoint_obj = ProxmoxEndpoint.objects.all()
        netbox_endpoint_obj = NetBoxEndpoint.objects.all()
        fastapi_endpoint_obj = FastAPIEndpoint.objects.all()

        fastapi_info = {}
        if fastapi_endpoint_obj:
            fastapi_info = get_fastapi_url(fastapi_endpoint_obj[0])

        return render(
            request,
            self.template_name,
            {
                "default_config": default_config,
                "proxmox_endpoint_list": proxmox_endpoint_obj if proxmox_endpoint_obj.exists() else None,
                "netbox_endpoint_list": netbox_endpoint_obj if netbox_endpoint_obj.exists() else None,
                "fastapi_endpoint_list": fastapi_endpoint_obj if fastapi_endpoint_obj.exists() else None,
                "fastapi_url": fastapi_info.get("http_url", fastapi_example_url),
                "fastapi_websocket_url": fastapi_info.get("websocket_url", fastapi_example_websocket_url),
            },
        )


class TestWebSocketView(View):
    template_name = "netbox_proxbox/test/websocket.html"

    def get(self, request):
        fastapi_object = FastAPIEndpoint.objects.first()
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


class NodesView(View):
    template = "netbox_proxbox/devices.html"

    def get(self, request):
        plugin_configuration = getattr(configuration, "PLUGINS_CONFIG", {})
        return render(request, self.template, {"configuration": plugin_configuration})


class VirtualMachinesView(View):
    template = "netbox_proxbox/virtual_machines.html"

    def get(self, request):
        plugin_configuration = getattr(configuration, "PLUGINS_CONFIG", {})
        return render(request, self.template, {"configuration": plugin_configuration})


class ContributingView(View):
    template_name = "netbox_proxbox/contributing.html"

    def get(self, request):
        return render(
            request,
            self.template_name,
            {
                "html": github.get(filename="CONTRIBUTING.md"),
                "title": "Contributing to Proxbox Project",
            },
        )


class CommunityView(View):
    template_name = "netbox_proxbox/community.html"

    def get(self, request):
        return render(request, self.template_name, {"title": "Join our Community!"})
