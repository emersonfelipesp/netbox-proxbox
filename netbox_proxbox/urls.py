#from django.<a href="http" target="_blank">http</a> import HttpResponse
from django.http import HttpResponse
from django.urls import path

from .views import (
    ProxmoxVMCreateView,
    ProxmoxVMDeleteView,
    ProxmoxVMEditView,
    ProxmoxVMListView,
    ProxmoxVMView,
)

urlpatterns = [
    path("", ProxmoxVMListView.as_view(), name="proxmoxvm_list"),
    # <int:pk> = plugins/netbox_proxmoxvm/<pk> | example: plugins/netbox_proxmoxvm/1/
    # ProxmoxVMView.as_view() - as.view() is need so that our view class can process requests.
    # as_view() takes request and returns well-formed response, that is a class based view.
    path("<int:pk>/", ProxmoxVMView.as_view(), name="proxmoxvm"),
    path("add/", ProxmoxVMCreateView.as_view(), name="proxmoxvm_add"),
    path("<int:pk>/delete/", ProxmoxVMDeleteView.as_view(), name="proxmoxvm_delete"),
    path("<int:pk>/edit/", ProxmoxVMEditView.as_view(), name="proxmoxvm_edit"),
]
