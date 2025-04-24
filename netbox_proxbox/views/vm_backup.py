# NetBox Imports
from netbox.views import generic
from utilities.views import register_model_view, ViewTab
from django.shortcuts import render
from virtualization.models import VirtualMachine

import requests

# Proxbox Imports
from netbox_proxbox.models import VMBackup, FastAPIEndpoint
from netbox_proxbox.tables import VMBackupTable
from netbox_proxbox.filtersets import VMBackupFilterSet
from netbox_proxbox.forms import VMBackupForm, VMBackupFilterForm
from netbox_proxbox.utils import get_fastapi_url

import logging
logger = logging.getLogger(__name__)

__all__ = (
    'VMBackupView',
    'VMBackupListView',
    'VMBackupEditView',
    'VMBackupDeleteView',
    'VMBackupBulkDeleteView',
    'VMBackupTabView',
) 


@register_model_view(VirtualMachine, 'backups', path='backups')
class VMBackupTabView(generic.ObjectView):
    """
    A tab view that displays backups associated with a VirtualMachine instance.
    
    This view integrates into NetBox's VirtualMachine detail page as a tab,
    showing all backups related to the specific virtual machine.
    
    Attributes:
        queryset: QuerySet filtering VirtualMachine objects
        template_name: Path to the template that renders the backup list
        tab: ViewTab configuration for UI integration
            - label: Display name of the tab ("Backups")
            - badge: Shows count of associated backups
            - permission: Required permission to view the tab
            - weight: Tab ordering position (higher numbers appear later)
    
    URL Pattern:
        Accessible at /virtualization/virtual-machines/<pk>/backups/
    
    Permissions Required:
        - netbox_proxbox.view_vmbackup
    
    Template Context:
        - object: The VirtualMachine instance being viewed
        - table: Configured VMBackupTable instance showing related backups
        - tab: ViewTab instance for UI rendering
    
    Example:
        A virtual machine with ID 123 would show its backups at:
        /virtualization/virtual-machines/123/backups/
    """
    queryset = VirtualMachine.objects.all()
    template_name = 'netbox_proxbox/virtual_machine_backups.html'
    
    tab = ViewTab(
        label='Backups',
        badge=lambda obj: VMBackup.objects.filter(virtual_machine=obj).count(),
        permission='netbox_proxbox.view_vmbackup',
        weight=1000
    )
    
    def get(self, request, pk):
        """
        Handle GET requests for the backup tab view.
        
        Args:
            request: The HTTP request object
            pk: Primary key of the VirtualMachine instance
            
        Returns:
            Rendered template response showing the backup table
            
        Note:
            Filters VMBackup objects to show only those associated 
            with the specific virtual machine instance.
        """
        instance = VirtualMachine.objects.get(pk=pk)
        table = VMBackupTable(VMBackup.objects.filter(virtual_machine=instance))
        table.configure(request)
        
        # Configure table to exclude virtual_machine column
        table.exclude = ('virtual_machine',)
        
        return render(
            request,
            self.template_name,
            {
                'object': instance,
                'table': table,
                'tab': self.tab,
            }
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
        'sync_backups': {'view'},
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