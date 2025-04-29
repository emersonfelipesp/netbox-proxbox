from rest_framework import serializers

from netbox.api.serializers import NetBoxModelSerializer
from netbox.api.fields import ContentTypeField
from extras.api.serializers import TagSerializer, JournalEntrySerializer
from ipam.api.serializers import IPAddressSerializer
from virtualization.api.serializers import VirtualMachineSerializer
from netbox_proxbox.models import (
    ProxmoxEndpoint,
    NetBoxEndpoint,
    FastAPIEndpoint,
    SyncProcess,
    VMBackup
)
from netbox_proxbox.choices import (
    SyncTypeChoices,
    SyncStatusChoices,
    ProxmoxBackupSubtypeChoices,
    ProxmoxBackupFormatChoices
)
# JournalEntryKindChoices is typically defined in the choices module of the NetBox codebase.
# Since we are dealing with a serializer related to journal entries, it is likely imported from extras.choices.
from extras.choices import JournalEntryKindChoices

from extras.models import Tag, JournalEntry
from virtualization.models import VirtualMachine
from django.contrib.contenttypes.models import ContentType

class VMBackupSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_proxbox-api:vmbackup-detail',
    )
    virtual_machine = VirtualMachineSerializer(nested=True)
    subtype = serializers.ChoiceField(choices=ProxmoxBackupSubtypeChoices)
    format = serializers.ChoiceField(choices=ProxmoxBackupFormatChoices)
    tags = TagSerializer(many=True, required=False, nested=True)
    
    class Meta:
        model = VMBackup
        fields = (
            'id', 'url', 'display', 'virtual_machine', 'subtype', 'format', 'creation_time', 'size', 'used', 'encrypted',
            'verification_state', 'verification_upid', 'volume_id', 'vmid', 'storage',
            'tags', 'custom_fields', 'created', 'last_updated',
        )
    

class SyncProcessSerializer(NetBoxModelSerializer):
    """
    Serializer for SyncProcess model.
    
    This serializer handles the conversion of SyncProcess objects to/from JSON.
    It extends NetBoxModelSerializer to support NetBox's standard features like tags and custom fields.
    
    Attributes:
        url: HyperlinkedIdentityField for the object's detail view
        sync_type: ChoiceField for sync process type
        status: ChoiceField for sync process status
        runtime: FloatField for process duration
        started_at: DateTimeField for process start time
        completed_at: DateTimeField for process completion time
        tags: TagSerializer for associated tags
        
    Fields:
        - id: Unique identifier
        - url: API endpoint URL
        - display: Human-readable display string
        - name: Process name
        - sync_type: Type of sync process
        - status: Current status
        - started_at: Start timestamp
        - completed_at: Completion timestamp
        - runtime: Process duration in seconds
        - tags: Associated tags
        - created: Creation timestamp
        - last_updated: Last update timestamp
    """
    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_proxbox-api:syncprocess-detail',
    )
    sync_type = serializers.ChoiceField(choices=SyncTypeChoices)
    status = serializers.ChoiceField(choices=SyncStatusChoices)
    runtime = serializers.FloatField(required=False, allow_null=True)
    started_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(required=False, allow_null=True)
    tags = TagSerializer(many=True, required=False, nested=True)
    
    class Meta:
        model = SyncProcess
        fields = (
            'id', 'url', 'display', 'name', 'sync_type', 'status', 'started_at', 'completed_at',
            'runtime', 'tags', 'created', 'last_updated',
        )

class ProxmoxEndpointSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_proxbox-api:endpoints:proxmox-endpoint-detail',
    )
    ip_address = IPAddressSerializer()
    domain = serializers.CharField(required=False, allow_null=True)
    
    class Meta:
        model = ProxmoxEndpoint
        fields = (
            'id', 'url', 'display', 'name', 'ip_address', 'domain', 'port',
            'token_name', 'token_value', 'username', 'password', 'verify_ssl',
            'mode', 'version', 'repoid', 
            'tags', 'custom_fields', 'created', 'last_updated',
        )


class NetBoxEndpointSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_proxbox-api:endpoints:netbox-endpoint-detail',
    )
    ip_address = IPAddressSerializer(nested=True, required=False, allow_null=True)
    
    class Meta:
        model = NetBoxEndpoint
        fields = (
            'id', 'url', 'display', 'name', 'ip_address', 'port',
            'token', 'verify_ssl', 'tags', 'custom_fields',
            'created', 'last_updated',
        )
    
    
    def create(self, validated_data):
        """
        Check if a NetBoxEndpoint already exists. If it does, return the existing one.
        Otherwise, create a new one.
        """
        if NetBoxEndpoint.objects.exists():
            return NetBoxEndpoint.objects.first()
        return super().create(validated_data)
    

class FastAPIEndpointSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_proxbox-api:endpoints:fastapi-endpoint-detail',
    )
    ip_address = IPAddressSerializer(nested=True, required=False, allow_null=True)
    
    class Meta:
        model = FastAPIEndpoint
        fields = (
            'id', 'url', 'display', 'name', 'ip_address', 'port',
            'verify_ssl', 'tags', 'custom_fields', 'created', 'last_updated',
        )

    def create(self, validated_data):
        """
        Check if a FastAPIEndpoint already exists. If it does, return the existing one.
        Otherwise, create a new one.
        """
        if FastAPIEndpoint.objects.exists():
            return FastAPIEndpoint.objects.first()
        return super().create(validated_data)

class JournalEntrySerializer(NetBoxModelSerializer):
    """
    Serializer for JournalEntry model.
    
    This serializer handles the conversion of JournalEntry objects to/from JSON,
    providing a standardized way to represent journal entries in the API.
    It extends NetBoxModelSerializer to support NetBox's standard features.
    
    Attributes:
        url: HyperlinkedIdentityField for the object's detail view
        object_type: ContentTypeField for the associated object type
        object_id: IntegerField for the associated object ID
        kind: ChoiceField for the entry type (info, success, warning, error)
        comments: CharField for the entry content
        tags: TagSerializer for associated tags
        
    Fields:
        - id: Unique identifier
        - url: API endpoint URL
        - display: Human-readable display string
        - object_type: Type of associated object
        - object_id: ID of associated object
        - kind: Entry type
        - comments: Entry content
        - tags: Associated tags
        - created: Creation timestamp
        - last_updated: Last update timestamp
        
    Example JSON:
        {
            "id": 1,
            "url": "/api/plugins/proxbox/journal-entries/1/",
            "display": "Info: Sync process started",
            "object_type": "netbox_proxbox.syncprocess",
            "object_id": 1,
            "kind": "info",
            "comments": "Sync process started",
            "tags": [],
            "created": "2024-01-01T00:00:00Z",
            "last_updated": "2024-01-01T00:00:00Z"
        }
    """
    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_proxbox-api:journalentry-detail',
    )
    object_type = ContentTypeField(
        queryset=ContentType.objects.all(),
        required=True,
    )
    object_id = serializers.IntegerField(required=True)
    kind = serializers.ChoiceField(choices=JournalEntryKindChoices)
    comments = serializers.CharField()
    tags = TagSerializer(many=True, required=False, nested=True)
    
    class Meta:
        model = JournalEntry
        fields = (
            'id', 'url', 'display', 'object_type', 'object_id', 'kind', 'comments',
            'tags', 'created', 'last_updated',
        )