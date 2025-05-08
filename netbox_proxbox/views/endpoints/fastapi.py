# Django Imports
from django.shortcuts import get_object_or_404
from django.urls import reverse

# NetBox Imports
from netbox.views import generic
from utilities.views import register_model_view

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


@register_model_view(FastAPIEndpoint)
class FastAPIEndpointView(generic.ObjectView):
    """
    Display a single FastAPI endpoint.
    """
    queryset = FastAPIEndpoint.objects.all()


@register_model_view(FastAPIEndpoint, 'list', path='', detail=False)
class FastAPIEndpointListView(generic.ObjectListView):
    """
    Display a list of FastAPI endpoints.
    """
    queryset = FastAPIEndpoint.objects.all()
    table = FastAPIEndpointTable
    filterset = FastAPIEndpointFilterSet
    filterset_form = FastAPIEndpointFilterForm


@register_model_view(FastAPIEndpoint, 'add', detail=False)
@register_model_view(FastAPIEndpoint, 'edit')
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
        # If there is already an existing FastAPIEndpoint object, return the first object
        if int(FastAPIEndpoint.objects.count()) >= 1:
            return FastAPIEndpoint.objects.first()
        
        if not kwargs:
            # We're creating a new object
            return self.queryset.model()
            
        # If there is no existing FastAPIEndpoint object, return the object with the given kwargs
        return get_object_or_404(FastAPIEndpoint.objects.all(), **kwargs)
    
    def get_extra_context(self, request, instance):
        # If there is already an existing FastAPIEndpoint object, pass True to the template
        if int(FastAPIEndpoint.objects.count()) >= 1:
            return {'existing_object': True}
        
        # If there is no existing FastAPIEndpoint object, pass False to the template
        return {'existing_object': False}


@register_model_view(FastAPIEndpoint, 'delete')
class FastAPIEndpointDeleteView(generic.ObjectDeleteView):
    """
    Delete a FastAPI endpoint.
    """
    queryset = FastAPIEndpoint.objects.all()
 