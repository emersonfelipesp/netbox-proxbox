from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
# 'View' is a django subclass. Basic type of class-based views
from django.views import View
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from django.views.decorators.cache import never_cache

# Enables permissions for views using Django authentication system.
# PermissionRequiredMixin = will handle permission checks logic and will plug into the
# Netbox's existing authorization system.
from django.contrib.auth.mixins import PermissionRequiredMixin

from .icon_classes import icon_classes
from .filters import ProxmoxVMFilter
from .forms import ProxmoxVMForm, ProxmoxVMFilterForm
from .models import ProxmoxVM
from .tables import ProxmoxVMTable, VMUpdateResult, NodeUpdateResult

from netbox_proxbox import proxbox_api
import json

from netbox import configuration

from . import ProxboxConfig

class HomeView(View):
    """Homepage"""
    template_name = 'netbox_proxbox/home.html'

    # service incoming GET HTTP requests
    def get(self, request):
        """Get request."""

        plugin_configuration = configuration.PLUGINS_CONFIG
        default_config = ProxboxConfig.default_settings

        return render(
            request,
            self.template_name,
            {
                "configuration": plugin_configuration,
                "default_config": default_config,
                "configuration_json": json.dumps(plugin_configuration, indent=4),
                "default_config_json": json.dumps(default_config, indent=4)
            }
        )

''' 
def table_data():
    json_result = proxbox_api.update.all(remove_unused = True)

    vm_table = []
    for row in json_result.get("virtualmachines"):
        json = {
            "name": row["name"],
            "status": row["changes"]["status"],
            "custom_fields": row["changes"]["custom_fields"],
            "local_context": row["changes"]["local_context"],
            "resources": row["changes"]["resources"],
            "tag": row["changes"]["tag"],
            "interfaces": row["changes"]["interfaces"],
            "ips": row["changes"]["ips"],
        }
        vm_table.append(json)

    virtualmachines_table = VMUpdateResult(vm_table)

    node_table = []
    for row in json_result.get("nodes"):
        json = {
            "status": row["changes"]["status"],
            "cluster": row["changes"]["cluster"],
            "interfaces": row["changes"]["interfaces"],
            "result": row["result"]
        }
        node_table.append(json)

    nodes_table = NodeUpdateResult(node_table)


    return [virtualmachines_table, nodes_table]
'''


class ProxmoxFullUpdate(PermissionRequiredMixin, View):
    """Full Update of Proxmox information on Netbox."""

    # Define permission
    permission_required = "netbox_proxbox.view_proxmoxvm"


    

    # service incoming GET HTTP requests
    # 'pk' value is passed to get() via URL defined in urls.py
    def get(self, request):
        """Get request."""

        json_result = proxbox_api.update.all(remove_unused = True)
        
        return render(
            request,
            "netbox_proxbox/proxmox_vm_full_update.html",
            {
                "proxmox": json_result,
                "proxmox_json": json.dumps(json_result, indent=4)
            },
        )


class ProxmoxVMView(PermissionRequiredMixin, View):
    """Display Virtual Machine details"""

    # specify permission required to access the view
    permission_required = "netbox_proxbox.view_proxmoxvm"

    # retrieve and filter objects on ProxmoxVM
    queryset = ProxmoxVM.objects.all()

    # service incoming GET HTTP requests
    # 'pk' value is passed to get() via URL defined in urls.py
    def get(self, request, pk):
        """Get request."""

        # get_object_or_404() returns 404 HTML code instead of raising internal exception
        # pk = primary key
        proxmoxvm_obj = get_object_or_404(self.queryset, pk=pk)

        # render() renders provided template and uses it to create a well-formed web response
        return render(
            request,
            "netbox_proxbox/proxmox_vm.html",
            {
                "proxmoxvm": proxmoxvm_obj,
            },
        )


class ProxmoxVMListView(PermissionRequiredMixin, View):
    """View for listing all existing Virtual Machines."""

    permission_required = "netbox_proxbox.view_proxmoxvm"

    # all of the objects should be given to the view
    queryset = ProxmoxVM.objects.all()

    filterset = ProxmoxVMFilter

    # form that will be rendered in list view template
    filterset_form = ProxmoxVMFilterForm

    def get(self, request):
        """Get request."""

        # where the filtering happens.
        # the filterset is fed with form values contained in request.GET and queryset with ProxmoxVM objects.
        # '.qs' = returns QuerySet like object what is assigned back to 'self.queryset'
        # the 'self.queryset' is then fed to table constructor
        self.queryset = self.filterset(request.GET, self.queryset).qs

        # table class
        
        table = ProxmoxVMTable(self.queryset)

        # RequestConfig is used to configure pagination of 25 object per page
        #RequestConfig(request, paginate={"per_page": 25}).configure(table)

        return render(
            request, "netbox_proxbox/proxmox_vm_list.html", 
            {
                "table": table,
                "filter_form": self.filterset_form(request.GET),
                "icon_classes": icon_classes,
            }
        )


# 'CreateView' is provided by Django
class ProxmoxVMCreateView(PermissionRequiredMixin, CreateView):
    """View for creating a new ProxmoxVM instance."""

    permission_required = "netbox_proxbox.add_proxmoxvm"

    form_class = ProxmoxVMForm
    template_name = "netbox_proxbox/proxmox_vm_edit.html"


class ProxmoxVMDeleteView(PermissionRequiredMixin, DeleteView):
    """View for deleting ProxmoxVM instance."""

    permission_required = "netbox_proxbox.delete_proxmoxvm"

    model = ProxmoxVM
    # reverse_lazy = function used to return the page for the given namespace URL
    # success_url = which view will redirect after an object has been deleted
    success_url = reverse_lazy("plugins:netbox_proxbox:proxmoxvm_list")

    # template_name = points to the template that will be rendred when asked to confirm the deletion
    template_name = "netbox_proxbox/proxmox_vm_delete.html"


class ProxmoxVMEditView(PermissionRequiredMixin, UpdateView):
    """View for editing a ProxmoxVM instance."""

    permission_required = "netbox_proxbox.change_proxmoxvm"

    model = ProxmoxVM
    form_class = ProxmoxVMForm
    template_name = "netbox_proxbox/proxmox_vm_edit.html"