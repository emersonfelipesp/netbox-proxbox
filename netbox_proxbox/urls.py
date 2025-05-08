from django.urls import include, path
from utilities.urls import get_model_urls

from netbox_proxbox.websocket_client import websocket_client, WebSocketView

from netbox.views.generic import ObjectChangeLogView

from netbox_proxbox import models, views

app_name = 'netbox_proxbox'

urlpatterns = [
    # Home View
    path('', views.HomeView.as_view(), name='home'),
    path('nodes', views.NodesView.as_view(), name='nodes'),
    path('virtual_machines', views.VirtualMachinesView.as_view(), name='virtual_machines'),
    path('contributing/', views.ContributingView.as_view(), name='contributing'),
    path('community/', views.CommunityView.as_view(), name='community'),
    
    path('fix-proxbox-backend/', views.FixProxboxBackendView.as_view(), name='fix-proxbox-backend'),
    path('start-proxbox-backend/', views.FixProxboxBackendView.as_view(), name='start-proxbox-backend'),
    path('stop-proxbox-backend/', views.StopProxboxBackendView.as_view(), name='stop-proxbox-backend'),
    path('restart-proxbox-backend/', views.RestartProxboxBackendView.as_view(), name='restart-proxbox-backend'),
    path('status-proxbox-backend/', views.StatusProxboxBackendView.as_view(), name='status-proxbox-backend'),

    # Redirect to: "https://github.com/orgs/netdevopsbr/discussions"
    path('discussions/', views.DiscussionsView, name='discussions'),
    path('discord/', views.DiscordView, name='discord'),
    path('telegram/', views.TelegramView, name='telegram'),
    
    # ProxmoxEndpoint Model URLs
    path('endpoints/proxmox/<int:pk>/', include(get_model_urls('netbox_proxbox', 'proxmoxendpoint'))),
    path('endpoints/proxmox/', include(get_model_urls('netbox_proxbox', 'proxmoxendpoint', detail=False))),
    
    # NetBoxEndpoint Model URLs
    path('endpoints/netbox/<int:pk>/', include(get_model_urls('netbox_proxbox', 'netboxendpoint'))),
    path('endpoints/netbox/', include(get_model_urls('netbox_proxbox', 'netboxendpoint', detail=False))),
    
    # FastAPIEndpoint Model URLs
    path('endpoints/fastapi/<int:pk>/', include(get_model_urls('netbox_proxbox', 'fastapiendpoint'))),
    path('endpoints/fastapi/', include(get_model_urls('netbox_proxbox', 'fastapiendpoint', detail=False))),
    
    # SyncProcess Model URLs
    path('sync-processes/<int:pk>/', include(get_model_urls('netbox_proxbox', 'syncprocess'))),
    path('sync-processes/', include(get_model_urls('netbox_proxbox', 'syncprocess', detail=False))),
    
    # VMBackup Model URLs
    path('backups/<int:pk>/', include(get_model_urls('netbox_proxbox', 'vmbackup'))),
    path('backups/', include(get_model_urls('netbox_proxbox', 'vmbackup', detail=False))),
    
    # Manual Sync (HTTP Request)
    path('sync/devices', views.sync_devices, name='sync_devices'),
    path('sync/virtual-machines', views.sync_virtual_machines, name='sync_virtual_machines'),
    path('sync/virtual-machines/backups', views.sync_vm_backups, name='sync_vm_backups'),
    path('sync/full-update', views.sync_full_update, name='sync_full_update'),
    
    path('keepalive-status/<str:service>/<int:pk>', views.get_service_status, name='keepalive_status'),
    path('proxmox-card/<int:pk>', views.get_proxmox_card, name='proxmox_card'),
    path('websocket/<str:message>', WebSocketView.as_view(), name='websocket'),
]