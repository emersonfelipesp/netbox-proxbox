# Django Imports
from django.shortcuts import get_object_or_404
from django.urls import reverse

# NetBox Imports
from netbox.views import generic

# ProxBox Imports
from netbox_proxbox.models import FastAPIEndpoint
from netbox_proxbox.tables import FastAPIEndpointTable
from netbox_proxbox.filtersets import FastAPIEndpointFilterSet
from netbox_proxbox.forms import FastAPIEndpointForm, FastAPIEndpointFilterForm


__all__ = (
    'FastAPIEndpointView',
    'FastAPIEndpointListView',
    'FastAPIEndpointEditView',
    'FastAPIEndpointDeleteView',
)


class FastAPIEndpointView(generic.ObjectView):
    queryset = FastAPIEndpoint.objects.all()


class FastAPIEndpointListView(generic.ObjectListView):
    queryset = FastAPIEndpoint.objects.all()
    table = FastAPIEndpointTable
    filterset = FastAPIEndpointFilterSet
    filterset_form = FastAPIEndpointFilterForm


class FastAPIEndpointEditView(generic.ObjectEditView):
    """
    This view is used to edit and create the FastAPIEndpoint object.
    
    If there is already an existing FastAPIEndpoint object,
    the view will return the existing object, allowing only one object to be created.
    """
    template_name = 'netbox_proxbox/fastapiendpoint_edit.html'
    queryset = FastAPIEndpoint.objects.all()
    form = FastAPIEndpointForm
    
    def get_object(self, **kwargs):
        if int(FastAPIEndpoint.objects.count()) >= 1:
            return FastAPIEndpoint.objects.first()
    
        if not kwargs:
            # We're creating a new object
            return self.queryset.model()
        
        return get_object_or_404(FastAPIEndpoint.objects.all(), **kwargs)
    
    def get_extra_context(self, request, instance):
        if int(FastAPIEndpoint.objects.count()) >= 1:
            return {'existing_object': True,}
        
        return {'existing_object': False}


class FastAPIEndpointDeleteView(generic.ObjectDeleteView):
    queryset = FastAPIEndpoint.objects.all()
 