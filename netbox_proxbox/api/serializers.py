from rest_framework import serializers

from netbox.api.serializers import NetBoxModelSerializer
from ipam.api.serializers import IPAddressSerializer
from ..models import ProxmoxEndpoint, NetBoxEndpoint


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

