from django.shortcuts import get_object_or_404, render

# 'View' is a django subclass. Basic type of class-based views
from django.views import View

from django_tables2 import RequestConfig

from django.views.generic.edit import CreateView

from .models import VmResources
from .tables import VmResourcesTable
from .forms import VmResourcesForm

class VmResourcesView(View):
    """Display Virtual Machine details"""

    # retrieve and filter objects on VmResources
    queryset = VmResources.objects.all()

    # service incoming GET HTTP requests
    # 'pk' value is passed to get() via URL defined in urls.py
    def get(self, request, pk):
        """Get request."""

        # get_object_or_404() returns 404 HTML code instead of raising internal exception
        # pk = primary key
        vmresources_obj = get_object_or_404(self.queryset, pk=pk)

        # render() renders provided template and uses it to create a well-formed web response
        return render(
            request,
            "netbox_proxbox/vm_resources.html",
            {
                "vmresources": vmresources_obj,
            },
        )

class VmResourcesListView(View):
    """View for listing all existing Virtual Machines."""

    # all of the objects should be given to the view
    queryset = VmResources.objects.all()

    def get(self, request):
        """Get request."""

        # table class
        table = VmResourcesTable(self.queryset)

        # RequestConfig is used to configure pagination of 25 object per page
        RequestConfig(request, paginate={"per_page": 25}).configure(table)

        return render(
            request, "netbox_proxbox/vm_resources_list.html", {"table": table}
        )

# 'CreateView' is provided by Django
class VmResourcesCreateView(CreateView):
    """View for creating a new BgpPeering instance."""

    form_class = VmResourcesForm
    template_name = "netbox_proxbox/vm_resources_edit.html"