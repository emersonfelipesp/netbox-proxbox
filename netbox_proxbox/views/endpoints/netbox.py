# Django Imports
from django.shortcuts import get_object_or_404
from django.urls import reverse

# NetBox Imports
from netbox.views import generic

# ProxBox Imports
from netbox_proxbox.models import NetBoxEndpoint
from netbox_proxbox.tables import NetBoxEndpointTable
from netbox_proxbox.filtersets import NetBoxEndpointFilterSet
from netbox_proxbox.forms import NetBoxEndpointForm, NetBoxEndpointFilterForm


__all__ = (
    'NetBoxEndpointView',
    'NetBoxEndpointListView',
    'NetBoxEndpointEditView',
    'NetBoxEndpointDeleteView',
)


class NetBoxEndpointView(generic.ObjectView):
    queryset = NetBoxEndpoint.objects.all()


class NetBoxEndpointListView(generic.ObjectListView):
    queryset = NetBoxEndpoint.objects.all()
    table = NetBoxEndpointTable
    filterset = NetBoxEndpointFilterSet
    filterset_form = NetBoxEndpointFilterForm


class NetBoxEndpointEditView(generic.ObjectEditView):
    """
    This view is used to edit and create the NetBoxEndpoint object.
    
    If there is already an existing NetBoxEndpoint object,
    the view will return the existing object, allowing only one object to be created.
    """
    
    template_name = 'netbox_proxbox/netboxendpoint_edit.html'
    queryset = NetBoxEndpoint.objects.all()
    form = NetBoxEndpointForm
    
    def get_object(self, **kwargs):
        # If there is already an existing NetBoxEndpoint object, return the first object
        if int(NetBoxEndpoint.objects.count()) >= 1:
            return NetBoxEndpoint.objects.first()
        
        if not kwargs:
            # We're creating a new object
            return self.queryset.model()
            
        # If there is no existing NetBoxEndpoint object, return the object with the given kwargs
        return get_object_or_404(NetBoxEndpoint.objects.all(), **kwargs)
    
    def get_extra_context(self, request, instance):
        # If there is already an existing NetBoxEndpoint object, pass True to the template
        if int(NetBoxEndpoint.objects.count()) >= 1:
            return {'existing_object': True}
        
        # If there is no existing NetBoxEndpoint object, pass False to the template
        return {'existing_object': False}


class NetBoxEndpointDeleteView(generic.ObjectDeleteView):
    queryset = NetBoxEndpoint.objects.all()

    