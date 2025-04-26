# NetBox Imports
from netbox.views import generic
from utilities.views import ViewTab, register_model_view
from extras.models import JournalEntry
from django.shortcuts import render
from django.contrib.contenttypes.models import ContentType

# Proxbox Imports
from netbox_proxbox.models import SyncProcess
from netbox_proxbox.tables import SyncProcessTable
from netbox_proxbox.filtersets import SyncProcessFilterSet
from netbox_proxbox.forms import SyncProcessForm, SyncProcessFilterForm

__all__ = (
    'SyncProcessView',
    'SyncProcessViewTab',
    'SyncProcessListView',
    'SyncProcessEditView',
    'SyncProcessDeleteView',
)

class SyncProcessView(generic.ObjectView):
    """
    Display a single sync process.
    """
    queryset = SyncProcess.objects.all()

@register_model_view(SyncProcess, 'journal', path='journal')
class SyncProcessViewTab(generic.ObjectView):
    """
    Display journal entries for a sync process.
    
    This view integrates into NetBox's SyncProcess detail page as a tab,
    showing all journal entries related to the specific sync process.
    
    Attributes:
        queryset: QuerySet filtering SyncProcess objects
        template_name: Path to the template that renders the journal entries
        tab: ViewTab configuration for UI integration
            - label: Display name of the tab ("Journal")
            - badge: Shows count of associated journal entries
            - permission: Required permission to view the tab
            - weight: Tab ordering position (higher numbers appear later)
    
    URL Pattern:
        Accessible at /plugins/netbox-proxbox/sync-process/<pk>/journal/
    
    Permissions Required:
        - extras.view_journalentry
    
    Template Context:
        - object: The SyncProcess instance being viewed
        - table: Configured JournalEntryTable instance showing related entries
        - form: Form for adding new journal entries (if user has permission)
        - tab: ViewTab instance for UI rendering
    """
    queryset = SyncProcess.objects.all()
    template_name = 'extras/object_journal.html'
    
    tab = ViewTab(
        label='Journal',
        badge=lambda obj: JournalEntry.objects.filter(
            assigned_object_type=ContentType.objects.get_for_model(obj),
            assigned_object_id=obj.id
        ).count(),
        permission='extras.view_journalentry',
        weight=9000
    )

    def get(self, request, pk):
        """
        Handle GET requests for the journal tab view.
        
        Args:
            request: The HTTP request object
            pk: Primary key of the SyncProcess instance
            
        Returns:
            Rendered template response showing the journal entries table
        """
        instance = self.get_object(pk=pk)
        content_type = ContentType.objects.get_for_model(instance)
        
        # Get journal entries for this object
        journal_entries = JournalEntry.objects.filter(
            assigned_object_type=content_type,
            assigned_object_id=instance.id
        )
        
        # Create table for journal entries
        from extras.tables import JournalEntryTable
        table = JournalEntryTable(journal_entries)
        table.configure(request)
        
        # Get journal entry form if user has permission
        from extras.forms import JournalEntryForm
        if request.user.has_perm('extras.add_journalentry'):
            form = JournalEntryForm(
                initial={
                    'assigned_object_type': content_type,
                    'assigned_object_id': instance.id
                }
            )
        else:
            form = None

        # Set base template because extras/object_journal.html expects a base template
        base_template = f"{instance._meta.app_label}/{instance._meta.model_name}.html"

        return render(request, self.template_name, {
            'object': instance,
            'table': table,
            'form': form,
            'tab': self.tab,
            'base_template': base_template,
        })

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

