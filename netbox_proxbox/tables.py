import django_tables2 as tables
from netbox.tables import NetBoxTable
from netbox.tables.columns import BooleanColumn

from .models import (
    ProxmoxEndpoint,
    NetboxEndpoint,
    FastAPIEndpoint,
)

class ProxmoxEndpointTable(NetBoxTable):
    name = tables.Column(linkify=True)
    verify_ssl = BooleanColumn()
    
    class Meta(NetBoxTable.Meta):
        model = ProxmoxEndpoint
        fields = (
            'pk',
            'name',
            'ip_address',
            'port',
            'mode',
            'version',
            'repoid',
            'username',
            'token_name',
            'verify_ssl'
        )
        
        default_columns = (
            'pk',
            'name',
            'ip_address',
            'port',
            'mode',
            'version',
        )