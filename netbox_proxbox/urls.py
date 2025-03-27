from django.urls import include, path
from utilities.urls import get_model_urls

from netbox_proxbox.websocket_client import websocket_client, WebSocketView

from netbox.views.generic import ObjectChangeLogView

from . import models, views

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
    path('endpoints/proxmox/', views.ProxmoxEndpointListView.as_view(), name='proxmoxendpoint_list'),
    path('endpoints/proxmox/add/', views.ProxmoxEndpointEditView.as_view(), name='proxmoxendpoint_add'),
    path('endpoints/proxmox/<int:pk>', views.ProxmoxEndpointView.as_view(), name='proxmoxendpoint'),
    path('endpoints/proxmox/<int:pk>/edit/', views.ProxmoxEndpointEditView.as_view(), name='proxmoxendpoint_edit'),
    path('endpoints/proxmox/<int:pk>/delete/', views.ProxmoxEndpointDeleteView.as_view(), name='proxmoxendpoint_delete'),
    path('endpoints/proxmox/<int:pk>/changelog/', ObjectChangeLogView.as_view(), name='proxmoxendpoint_changelog', kwargs={
        'model': models.ProxmoxEndpoint
    }),
    
    # NetBoxEndpoint Model URLs
    path('endpoints/netbox/', views.NetBoxEndpointListView.as_view(), name='netboxendpoint_list'),
    path('endpoints/netbox/add/', views.NetBoxEndpointEditView.as_view(), name='netboxendpoint_add'),
    path('endpoints/netbox/<int:pk>', views.NetBoxEndpointView.as_view(), name='netboxendpoint'),
    path('endpoints/netbox/<int:pk>/edit/', views.NetBoxEndpointEditView.as_view(), name='netboxendpoint_edit'),
    path('endpoints/netbox/<int:pk>/delete/', views.NetBoxEndpointDeleteView.as_view(), name='netboxendpoint_delete'),
    path('endpoints/netbox/<int:pk>/changelog/', ObjectChangeLogView.as_view(), name='netboxendpoint_changelog', kwargs={
        'model': models.NetBoxEndpoint
    }),
    
    
    # FastAPIEndpoint Model URLs
    path('endpoints/fastapi/', views.FastAPIEndpointListView.as_view(), name='fastapiendpoint_list'),
    path('endpoints/fastapi/add/', views.FastAPIEndpointEditView.as_view(), name='fastapiendpoint_add'),
    path('endpoints/fastapi/<int:pk>', views.FastAPIEndpointView.as_view(), name='fastapiendpoint'),
    path('endpoints/fastapi/<int:pk>/edit/', views.FastAPIEndpointEditView.as_view(), name='fastapiendpoint_edit'),
    path('endpoints/fastapi/<int:pk>/delete/', views.FastAPIEndpointDeleteView.as_view(), name='fastapiendpoint_delete'),
    path('endpoints/fastapi/<int:pk>/changelog/', ObjectChangeLogView.as_view(), name='fastapiendpoint_changelog', kwargs={
        'model': models.FastAPIEndpoint
    }),
    
    # SyncProcess Model URLs
    path('sync-processes/', views.SyncProcessListView.as_view(), name='syncprocess_list'),
    path('sync-processes/add/', views.SyncProcessEditView.as_view(), name='syncprocess_add'),
    path('sync-processes/<int:pk>', views.SyncProcessView.as_view(), name='syncprocess'),
    path('sync-processes/<int:pk>/edit/', views.SyncProcessEditView.as_view(), name='syncprocess_edit'),
    path('sync-processes/<int:pk>/delete/', views.SyncProcessDeleteView.as_view(), name='syncprocess_delete'),
    path('sync-processes/<int:pk>/changelog/', ObjectChangeLogView.as_view(), name='syncprocess_changelog', kwargs={
        'model': models.SyncProcess
    }),
    
    # Manual Sync (HTTP Request)
    path('sync/devices', views.sync_devices, name='sync_devices'),
    path('sync/virtual-machines', views.sync_virtual_machines, name='sync_virtual_machines'),
    path('sync/full-update', views.sync_full_update, name='sync_full_update'),
    
    path('keepalive-status/<str:service>/<int:pk>', views.get_service_status, name='keepalive_status'),
    path('proxmox-card/<int:pk>', views.get_proxmox_card, name='proxmox_card'),
    path('websocket/<str:message>', WebSocketView.as_view(), name='websocket'),
    
]