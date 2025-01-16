from django.urls import include, path
from utilities.urls import get_model_urls

from . import views

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
    
    path('endpoints/proxmox/', views.ProxmoxEndpointListView.as_view(), name='proxmoxendpoint_list'),
    path('endpoints/proxmox/<int:pk>', views.ProxmoxEndpointView.as_view(), name='proxmoxendpoint'),
    path('endpoints/proxmox/add/', views.ProxmoxEndpointEditView.as_view(), name='proxmoxendpoint_add'),
]
