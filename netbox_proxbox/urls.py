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

from netbox_proxbox import proxbox_api
import json

# This function is located on the wrong place
# Lately, it will have it's own template to display full update result
def full_update_view(request):    
    update_all_result = proxbox_api.update.all()
    update_all_json = json.dumps(update_all_result, indent = 4)

    remove_all_result = proxbox_api.remove.all()
    remove_all_json = json.dumps(remove_all_result, indent= 4)

    html = "<html><body><h1>Update all Proxmox information</h1>{}<br><h1>Remove all useless information (like deleted VMs)</h1>{}</body></html>".format(update_all_json, remove_all_json)
    return HttpResponse(html)


urlpatterns = [
    path("", ProxmoxVMListView.as_view(), name="proxmoxvm_list"),
    # <int:pk> = plugins/netbox_proxmoxvm/<pk> | example: plugins/netbox_proxmoxvm/1/
    # ProxmoxVMView.as_view() - as.view() is need so that our view class can process requests.
    # as_view() takes request and returns well-formed response, that is a class based view.
    path("<int:pk>/", ProxmoxVMView.as_view(), name="proxmoxvm"),
    path("add/", ProxmoxVMCreateView.as_view(), name="proxmoxvm_add"),
    path("<int:pk>/delete/", ProxmoxVMDeleteView.as_view(), name="proxmoxvm_delete"),
    path("<int:pk>/edit/", ProxmoxVMEditView.as_view(), name="proxmoxvm_edit"),

    # Proxbox API full update
    #path("full_update/", ProxmoxVMFullUpdate.as_view(), name="proxmoxvm_full_update")
    path("full_update/", full_update_view, name="proxmoxvm_full_update")
]
