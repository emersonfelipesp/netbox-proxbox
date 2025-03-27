# NetBox Imports
from netbox.views import generic

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
)

class SyncProcessView(generic.ObjectView):
    """
    Display a single sync process.
    """
    queryset = SyncProcess.objects.all()

class SyncProcessListView(generic.ObjectListView):
    """
    Display a list of sync processes.
    """
    queryset = SyncProcess.objects.all()
    table = SyncProcessTable
    filterset = SyncProcessFilterSet
    filterset_form = SyncProcessFilterForm

class SyncProcessEditView(generic.ObjectEditView):
    """
    Edit a sync process.
    """
    queryset = SyncProcess.objects.all()
    form = SyncProcessForm

class SyncProcessDeleteView(generic.ObjectDeleteView):
    """
    Delete a sync process.
    """
    queryset = SyncProcess.objects.all()

