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
    
    # Redirect to: "https://github.com/orgs/netdevopsbr/discussions"
    path('discussions/', views.DiscussionsView, name='discussions'),
    path('discord/', views.DiscordView, name='discord'),
    path('telegram/', views.TelegramView, name='telegram'),
    
    # Base Views
    path("list/", views.ProxmoxVMListView.as_view(), name="proxmoxvm_list"),
    # <int:pk> = plugins/netbox_proxmoxvm/<pk> | example: plugins/netbox_proxmoxvm/1/
    # ProxmoxVMView.as_view() - as.view() is need so that our view class can process requests.
    # as_view() takes request and returns well-formed response, that is a class based view.
    path("<int:pk>/", views.ProxmoxVMView.as_view(), name="proxmoxvm"),
    path("add/", views.ProxmoxVMCreateView.as_view(), name="proxmoxvm_add"),
    path("<int:pk>/delete/", views.ProxmoxVMDeleteView.as_view(), name="proxmoxvm_delete"),
    path("<int:pk>/edit/", views.ProxmoxVMEditView.as_view(), name="proxmoxvm_edit"),

    # Proxbox API full update
    path("full_update/", views.ProxmoxFullUpdate.as_view(), name="proxmoxvm_full_update"),
    path("single_update/", views.ProxmoxSingleUpdate.as_view(), name="proxmoxvm_single_update")
]
