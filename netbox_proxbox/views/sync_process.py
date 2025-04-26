# NetBox Imports
from netbox.views import generic
from utilities.views import register_model_view
from django.shortcuts import render, redirect
from django.contrib import messages

# Proxbox Imports
from netbox_proxbox.models import SyncProcess
from netbox_proxbox.tables import SyncProcessTable
from netbox_proxbox.filtersets import SyncProcessFilterSet
from netbox_proxbox.forms import SyncProcessForm, SyncProcessFilterForm

__all__ = (
    'SyncProcessView',
    'SyncProcessListView',
    'SyncProcessEditView',
    'SyncProcessDeleteView',
    'SyncProcessAddView',
)

@register_model_view(SyncProcess)
class SyncProcessView(generic.ObjectView):
    """
    Display a single sync process.
    """
    queryset = SyncProcess.objects.all()

@register_model_view(SyncProcess, 'list', path='', detail=False)
class SyncProcessListView(generic.ObjectListView):
    """
    Display a list of sync processes.
    """
    queryset = SyncProcess.objects.all()
    table = SyncProcessTable
    filterset = SyncProcessFilterSet
    filterset_form = SyncProcessFilterForm

@register_model_view(SyncProcess, 'add', detail=False)
class SyncProcessAddView(generic.ObjectView):
    """
    This view is not allowed to be used.
    Adding sync processes through the UI is not supported.
    
    Although this view is not allowed to be used, it is still necessary to define it because @get_model_urls() 
    from utilities.urls import get_model_urls will raise an error if it is not defined.
    """
    queryset = SyncProcess.objects.none()  # Empty queryset since we don't need any objects
    
    def get(self, request):
        messages.error(request, "Adding sync processes through the UI is not supported. Sync processes can only be created through the plugin backend.")
        return redirect('plugins:netbox_proxbox:syncprocess_list')

@register_model_view(SyncProcess, 'edit')
class SyncProcessEditView(generic.ObjectEditView):
    """
    Edit a sync process.
    """
    queryset = SyncProcess.objects.all()
    form = SyncProcessForm

@register_model_view(SyncProcess, 'delete')
class SyncProcessDeleteView(generic.ObjectDeleteView):
    """
    Delete a sync process.
    """
    queryset = SyncProcess.objects.all()

