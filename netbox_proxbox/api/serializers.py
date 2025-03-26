from rest_framework import serializers

from netbox.api.serializers import NetBoxModelSerializer
from ipam.api.serializers import IPAddressSerializer
from ..models import ProxmoxEndpoint, NetBoxEndpoint, FastAPIEndpoint, SyncProcess
from ..choices import SyncTypeChoices, SyncStatusChoices

class SyncProcessSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_proxbox-api:syncprocess-detail',
    )
    sync_type = serializers.ChoiceField(choices=SyncTypeChoices)
    status = serializers.ChoiceField(choices=SyncStatusChoices)
    runtime = serializers.FloatField(required=False, allow_null=True)
    started_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(required=False, allow_null=True)
    
    class Meta:
        model = SyncProcess
        fields = (
            'id', 'url', 'display', 'name', 'sync_type', 'status', 'started_at', 'completed_at',
            'runtime', 'created', 'last_updated',
        )

class ProxmoxEndpointSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_proxbox-api:proxmoxendpoint-detail',
    )
    ip_address = IPAddressSerializer()
    
    class Meta:
        model = ProxmoxEndpoint
        fields = (
            'id', 'url', 'display', 'name', 'ip_address', 'port',
            'token_name', 'token_value', 'username', 'password', 'verify_ssl',
            'mode', 'version', 'repoid', 
            'tags', 'custom_fields', 'created', 'last_updated',
        )


class NetBoxEndpointSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_proxbox-api:netboxendpoint-detail',
    )
    ip_address = IPAddressSerializer()
    
    class Meta:
        model = NetBoxEndpoint
        fields = (
            'id', 'url', 'display', 'name', 'ip_address', 'port',
            'token', 'verify_ssl', 'tags', 'custom_fields',
            'created', 'last_updated',
        )


class FastAPIEndpointSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_proxbox-api:fastapiendpoint-detail',
    )
    ip_address = IPAddressSerializer()
    
    class Meta:
        model = FastAPIEndpoint
        fields = (
            'id', 'url', 'display', 'name', 'ip_address', 'port',
            'verify_ssl', 'tags', 'custom_fields', 'created', 'last_updated',
        )
