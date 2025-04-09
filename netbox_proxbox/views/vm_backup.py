# NetBox Imports
from netbox.views import generic

# Proxbox Imports
from netbox_proxbox.models import VMBackup
from netbox_proxbox.tables import VMBackupTable
from netbox_proxbox.filtersets import VMBackupFilterSet
from netbox_proxbox.forms import VMBackupForm, VMBackupFilterForm

__all__ = (
    'VMBackupView',
    'VMBackupListView',
    'VMBackupEditView',
    'VMBackupDeleteView',
)

class VMBackupView(generic.ObjectView):
    """
    Display a single VM backup.
    """
    queryset = VMBackup.objects.all()

class VMBackupListView(generic.ObjectListView):
    """
    Display a list of VM backups.
    """
    queryset = VMBackup.objects.all()
    table = VMBackupTable
    filterset = VMBackupFilterSet
    filterset_form = VMBackupFilterForm

class VMBackupEditView(generic.ObjectEditView):
    """
    This view is currently not allowed to be used.
    Edit a VM backup.
    """
    queryset = VMBackup.objects.all()
    form = VMBackupForm

class VMBackupDeleteView(generic.ObjectDeleteView):
    """
    This view is currently not allowed to be used.
    Delete a VM backup.
    """
    queryset = VMBackup.objects.all()