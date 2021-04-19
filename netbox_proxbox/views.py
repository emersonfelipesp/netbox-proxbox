from django.shortcuts import get_object_or_404, render

# 'View' is a django subclass. Basic type of class-based views
from django.views import View

from django_tables2 import RequestConfig

from django.views.generic.edit import CreateView

from .models import VmResources
from .tables import VmResourcesTable
from .forms import VmResourcesForm, VmResourcesFilterForm
from .filters import VmResourcesFilter
from .icon_classes import icon_classes


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

    filterset = VmResourcesFilter

    # form that will be rendered in list view template
    filterset_form = VmResourcesFilterForm

    def get(self, request):
        """Get request."""

        # where the filtering happens.
        # the filterset is fed with form values contained in request.GET and queryset with VmResources objects.
        # '.qs' = returns QuerySet like object what is assigned back to 'self.queryset'
        # the 'self.queryset' is then fed to table constructor
        self.queryset = self.filterset(request.GET, self.queryset).qs

        # table class
        
        table = VmResourcesTable(self.queryset)

        # RequestConfig is used to configure pagination of 25 object per page
        RequestConfig(request, paginate={"per_page": 25}).configure(table)

        return render(
            request, "netbox_proxbox/vm_resources_list.html", 
            {
                "table": table,
                "filter_form": self.filterset_form(request.GET),
                "icon_classes": icon_classes,
            }
        )

# 'CreateView' is provided by Django
class VmResourcesCreateView(CreateView):
    """View for creating a new BgpPeering instance."""

    form_class = VmResourcesForm
    template_name = "netbox_proxbox/vm_resources_edit.html"