"""Register plugin UI routes for pages, models, sync actions, and status checks."""

from django.urls import include, path

from utilities.urls import get_model_urls

from netbox_proxbox import views
from netbox_proxbox.websocket_client import WebSocketView

app_name = "netbox_proxbox"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("nodes/", views.NodesView.as_view(), name="nodes"),
    path(
        "virtual_machines/",
        views.VirtualMachinesView.as_view(),
        name="virtual_machines",
    ),
    path("contributing/", views.ContributingView.as_view(), name="contributing"),
    path("community/", views.CommunityView.as_view(), name="community"),
    path("discussions/", views.DiscussionsView, name="discussions"),
    path("discord/", views.DiscordView, name="discord"),
    path("telegram/", views.TelegramView, name="telegram"),
    path(
        "endpoints/proxmox/<int:pk>/",
        include(get_model_urls("netbox_proxbox", "proxmoxendpoint")),
    ),
    path(
        "endpoints/proxmox/",
        include(get_model_urls("netbox_proxbox", "proxmoxendpoint", detail=False)),
    ),
    path(
        "endpoints/netbox/<int:pk>/",
        include(get_model_urls("netbox_proxbox", "netboxendpoint")),
    ),
    path(
        "endpoints/netbox/",
        include(get_model_urls("netbox_proxbox", "netboxendpoint", detail=False)),
    ),
    path(
        "endpoints/fastapi/<int:pk>/",
        include(get_model_urls("netbox_proxbox", "fastapiendpoint")),
    ),
    path(
        "endpoints/fastapi/",
        include(get_model_urls("netbox_proxbox", "fastapiendpoint", detail=False)),
    ),
    path(
        "sync-processes/<int:pk>/",
        include(get_model_urls("netbox_proxbox", "syncprocess")),
    ),
    path(
        "sync-processes/",
        include(get_model_urls("netbox_proxbox", "syncprocess", detail=False)),
    ),
    path("backups/<int:pk>/", include(get_model_urls("netbox_proxbox", "vmbackup"))),
    path(
        "backups/", include(get_model_urls("netbox_proxbox", "vmbackup", detail=False))
    ),
    path("sync/devices/", views.sync_devices, name="sync_devices"),
    path("sync/devices/stream/", views.sync_devices_stream, name="sync_devices_stream"),
    path(
        "sync/virtual-machines/",
        views.sync_virtual_machines,
        name="sync_virtual_machines",
    ),
    path(
        "sync/virtual-machines/stream/",
        views.sync_virtual_machines_stream,
        name="sync_virtual_machines_stream",
    ),
    path(
        "sync/virtual-machines/backups/", views.sync_vm_backups, name="sync_vm_backups"
    ),
    path("sync/full-update/", views.sync_full_update, name="sync_full_update"),
    path(
        "sync/full-update/stream/",
        views.sync_full_update_stream,
        name="sync_full_update_stream",
    ),
    path(
        "keepalive-status/<str:service>/<int:pk>/",
        views.get_service_status,
        name="keepalive_status",
    ),
    path("proxmox-card/<int:pk>/", views.get_proxmox_card, name="proxmox_card"),
    path("websocket/<str:message>", WebSocketView.as_view(), name="websocket"),
]
