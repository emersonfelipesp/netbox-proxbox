#from django.<a href="http" target="_blank">http</a> import HttpResponse
from django.http import HttpResponse
from django.urls import path

from . import views

from netbox_proxbox import proxbox_api
import json

urlpatterns = [
    # Home View
    path('', views.HomeView.as_view(), name='home'),
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
    

    # Proxbox API full update
    path("full_update/", views.ProxmoxFullUpdate.as_view(), name="proxmoxvm_full_update"),
    #path("single_update/", views.ProxmoxSingleUpdate.as_view(), name="proxmoxvm_single_update"),
    #path("proxmox/cluster/", views.ProxmoxCluster.as_view(), name="proxmox_cluster"),
]
