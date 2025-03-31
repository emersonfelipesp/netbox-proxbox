from rest_framework import serializers

from netbox.api.serializers import NetBoxModelSerializer
from ipam.api.serializers import IPAddressSerializer
from ..models import ProxmoxEndpoint, NetBoxEndpoint, FastAPIEndpoint, SyncProcess
from ..choices import SyncTypeChoices, SyncStatusChoices
from extras.models import Tag

class SyncProcessSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_proxbox-api:syncprocess-detail',
    )
    sync_type = serializers.ChoiceField(choices=SyncTypeChoices)
    status = serializers.ChoiceField(choices=SyncStatusChoices)
    runtime = serializers.FloatField(required=False, allow_null=True)
    started_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(required=False, allow_null=True)
    tags = serializers.PrimaryKeyRelatedField(queryset=Tag.objects.all(), many=True)
    
    class Meta:
        model = SyncProcess
        fields = (
            'id', 'url', 'display', 'name', 'sync_type', 'status', 'started_at', 'completed_at',
            'runtime', 'tags', 'created', 'last_updated',
        )

class ProxmoxEndpointSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_proxbox-api:proxmoxendpoint-detail',
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
        view_name='plugins-api:netbox_proxbox-api:netboxendpoint-detail',
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
        view_name='plugins-api:netbox_proxbox-api:fastapiendpoint-detail',
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