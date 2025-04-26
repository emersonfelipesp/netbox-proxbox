from netbox.api.viewsets import NetBoxModelViewSet
from rest_framework import viewsets
from extras.models import JournalEntry
from extras.api.serializers import JournalEntrySerializer
from netbox_proxbox.models import SyncProcess
from netbox_proxbox.api.serializers import SyncProcessSerializer
from netbox_proxbox.api.filters import SyncProcessFilterSet
from netbox_proxbox.filtersets import SyncProcessFilterSet as SyncProcessFilterSetUI

from .. import filtersets, models
from .serializers import (
    ProxmoxEndpointSerializer,
    NetBoxEndpointSerializer,
    FastAPIEndpointSerializer,
    VMBackupSerializer
)


class VMBackupViewSet(NetBoxModelViewSet):
    queryset = models.VMBackup.objects.all()
    serializer_class = VMBackupSerializer
    filterset_class = filtersets.VMBackupFilterSet

class SyncProcessViewSet(NetBoxModelViewSet):
    queryset = SyncProcess.objects.all()
    serializer_class = SyncProcessSerializer
    filterset_class = SyncProcessFilterSet

class ProxmoxEndpointViewSet(NetBoxModelViewSet):
    queryset = models.ProxmoxEndpoint.objects.all()
    serializer_class = ProxmoxEndpointSerializer

class NetBoxEndpointViewSet(NetBoxModelViewSet):
    queryset = models.NetBoxEndpoint.objects.all()
    serializer_class = NetBoxEndpointSerializer


class FastAPIEndpointViewSet(NetBoxModelViewSet):
    queryset = models.FastAPIEndpoint.objects.all()
    serializer_class = FastAPIEndpointSerializer

class JournalEntryViewSet(NetBoxModelViewSet):
    """
    ViewSet for managing journal entries associated with SyncProcess objects.
    
    This ViewSet provides CRUD operations for journal entries and allows filtering
    entries by their associated SyncProcess object.
    
    Attributes:
        queryset: Base queryset of all JournalEntry objects
        serializer_class: JournalEntrySerializer for data serialization
        
    Methods:
        get_queryset: Filters journal entries by SyncProcess object_id if provided
        
    API Endpoints:
        GET /api/plugins/proxbox/journal-entries/ - List all journal entries
        GET /api/plugins/proxbox/journal-entries/?object_id=<id> - Filter by SyncProcess
        POST /api/plugins/proxbox/journal-entries/ - Create new entry
        PUT /api/plugins/proxbox/journal-entries/<id>/ - Update entry
        DELETE /api/plugins/proxbox/journal-entries/<id>/ - Delete entry
        
    Example Usage:
        # Get all journal entries for a specific SyncProcess
        GET /api/plugins/proxbox/journal-entries/?object_id=1
        
        # Create a new journal entry
        POST /api/plugins/proxbox/journal-entries/
        {
            "assigned_object_type": "syncprocess",
            "assigned_object_id": 1,
            "kind": "info",
            "comments": "Sync process started"
        }
    """
    queryset = JournalEntry.objects.all()
    serializer_class = JournalEntrySerializer
    
    def get_queryset(self):
        """
        Filter journal entries by SyncProcess object_id if provided in query params.
        
        This method extends the base queryset to allow filtering journal entries
        by their associated SyncProcess object. When the 'object_id' query parameter
        is present, it filters the queryset to only include entries for that specific
        SyncProcess.
        
        Returns:
            QuerySet: Filtered queryset of JournalEntry objects
            
        Example:
            # Get all journal entries for SyncProcess with ID 1
            queryset = JournalEntry.objects.filter(
                assigned_object_type__model='syncprocess',
                assigned_object_id=1
            )
        """
        queryset = super().get_queryset()
        if 'object_id' in self.request.query_params:
            queryset = queryset.filter(
                assigned_object_type__model='syncprocess',
                assigned_object_id=self.request.query_params['object_id']
            )
        return queryset

    