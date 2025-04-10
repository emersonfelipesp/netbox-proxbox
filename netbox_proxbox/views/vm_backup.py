# NetBox Imports
from netbox.views import generic
from utilities.views import register_model_view

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
    'VMBackupBulkDeleteView',
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
    template_name = 'netbox_proxbox/vmbackup_list.html'
    actions = {
        'bulk_delete': {'delete'},
        'export': {'view'},
    }
    
    def get_required_permission(self):
        # Override to bypass permission check
        return 'netbox_proxbox.delete_vmbackup'

@register_model_view(VMBackup, 'bulk_delete', path='delete', detail=False)
class VMBackupBulkDeleteView(generic.BulkDeleteView):
    """
    Delete multiple VM backups.
    """
    queryset = VMBackup.objects.all()
    filterset = VMBackupFilterSet
    table = VMBackupTable
    
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