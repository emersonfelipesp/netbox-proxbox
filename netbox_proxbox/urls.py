"""Register plugin UI routes for pages, models, sync actions, and status checks."""

from django.urls import include, path
from utilities.urls import get_model_urls

from netbox_proxbox import views
from netbox_proxbox.websocket_client import WebSocketView

app_name = "netbox_proxbox"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("nodes/", views.NodesView.as_view(), name="nodes"),
    path(
        "virtual_machines/",
        views.VirtualMachinesView.as_view(),
        name="virtual_machines",
    ),
    path(
        "lxc_containers/",
        views.LXCContainersView.as_view(),
        name="lxc_containers",
    ),
    path("interfaces/", views.InterfacesView.as_view(), name="interfaces"),
    path("ip-addresses/", views.IPAddressesView.as_view(), name="ip_addresses"),
    path("contributing/", views.ContributingView.as_view(), name="contributing"),
    path("community/", views.CommunityView.as_view(), name="community"),
    path("discussions/", views.discussions_redirect, name="discussions"),
    path("discord/", views.discord_redirect, name="discord"),
    path("telegram/", views.telegram_redirect, name="telegram"),
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
        "storage/<int:pk>/",
        include(get_model_urls("netbox_proxbox", "proxmoxstorage")),
    ),
    path(
        "storage/",
        include(get_model_urls("netbox_proxbox", "proxmoxstorage", detail=False)),
    ),
    path("backups/<int:pk>/", include(get_model_urls("netbox_proxbox", "vmbackup"))),
    path(
        "backups/", include(get_model_urls("netbox_proxbox", "vmbackup", detail=False))
    ),
    path(
        "backup-routines/<int:pk>/",
        include(get_model_urls("netbox_proxbox", "backuproutine")),
    ),
    path(
        "backup-routines/",
        include(get_model_urls("netbox_proxbox", "backuproutine", detail=False)),
    ),
    path(
        "replications/<int:pk>/",
        include(get_model_urls("netbox_proxbox", "replication")),
    ),
    path(
        "replications/",
        include(get_model_urls("netbox_proxbox", "replication", detail=False)),
    ),
    path(
        "snapshots/<int:pk>/", include(get_model_urls("netbox_proxbox", "vmsnapshot"))
    ),
    path(
        "snapshots/",
        include(get_model_urls("netbox_proxbox", "vmsnapshot", detail=False)),
    ),
    path(
        "task-history/<int:pk>/",
        include(get_model_urls("netbox_proxbox", "vmtaskhistory")),
    ),
    path(
        "task-history/",
        include(get_model_urls("netbox_proxbox", "vmtaskhistory", detail=False)),
    ),
    path("sync/devices/", views.sync_devices, name="sync_devices"),
    path("sync/storage/", views.sync_storage, name="sync_storage"),
    path(
        "sync/selected/virtual-machines/",
        views.sync_selected_virtual_machines,
        name="sync_selected_virtual_machines",
    ),
    path(
        "sync/selected/backups/",
        views.sync_selected_vm_backups,
        name="sync_selected_vm_backups",
    ),
    path(
        "sync/selected/snapshots/",
        views.sync_selected_vm_snapshots,
        name="sync_selected_vm_snapshots",
    ),
    path(
        "sync/selected/storage/",
        views.sync_selected_storage,
        name="sync_selected_storage",
    ),
    path(
        "sync/selected/task-history/",
        views.sync_selected_vm_task_history,
        name="sync_selected_vm_task_history",
    ),
    path(
        "sync/virtual-machines/",
        views.sync_virtual_machines,
        name="sync_virtual_machines",
    ),
    path(
        "sync/virtual-machines/backups/", views.sync_vm_backups, name="sync_vm_backups"
    ),
    path(
        "sync/virtual-machines/snapshots/",
        views.sync_vm_snapshots,
        name="sync_vm_snapshots",
    ),
    path(
        "sync/backup-routines/",
        views.sync_backup_routines,
        name="sync_backup_routines",
    ),
    path(
        "sync/replications/",
        views.sync_replications,
        name="sync_replications",
    ),
    path(
        "sync/virtual-machines/virtual-disks/",
        views.sync_virtual_disks,
        name="sync_virtual_disks",
    ),
    path(
        "sync/network-interfaces/",
        views.sync_network_interfaces,
        name="sync_network_interfaces",
    ),
    path(
        "sync/ip-addresses/",
        views.sync_ip_addresses,
        name="sync_ip_addresses",
    ),
    path("sync/full-update/", views.sync_full_update, name="sync_full_update"),
    path("sync/schedule/", views.ScheduleSyncView.as_view(), name="schedule_sync"),
    path("settings/", views.SettingsView.as_view(), name="settings"),
    path(
        "sync/schedule/quick/",
        views.QuickScheduleSyncFromHomeView.as_view(),
        name="schedule_sync_quick",
    ),
    path(
        "keepalive-status/<str:service>/<int:pk>/",
        views.get_service_status,
        name="keepalive_status",
    ),
    path("proxmox-card/<int:pk>/", views.get_proxmox_card, name="proxmox_card"),
    path("websocket/<str:message>", WebSocketView.as_view(), name="websocket"),
    path("jobs/<int:pk>/stream/", views.JobStreamSSEView.as_view(), name="job_stream"),
    path("logs/", views.BackendLogsView.as_view(), name="backend_logs"),
    path(
        "logs/path/",
        views.BackendLogPathUpdateView.as_view(),
        name="backend_logs_path_update",
    ),
]
